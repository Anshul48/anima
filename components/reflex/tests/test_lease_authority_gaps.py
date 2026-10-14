"""Gap-fill negatives for the lease/action-authority repair (conditions 2-4).

Each test pins a fail-closed behavior on a fake substrate sink with exact
event counts. No real input, no real browser.
"""

from __future__ import annotations

import unittest
from typing import Any, Dict, List, Optional, Tuple

from reflex.cognition.skills.executor import SkillReplayExecutor
from reflex.episodes.replay_runner import EpisodeReplayRunner
from reflex.execution.browser.cdp_action_adapter import CDPActionAdapter
from reflex.execution.native.linux_input import (
    LinuxNativeInputAdapter,
    MockLinuxInputSubstrate,
)
from reflex.host.identity.lease_manager import (
    ActionLease,
    ActionLeaseManager,
    InvalidLeaseError,
)
from reflex.host.kernel.host_kernel import DispatchState, HostControlKernel
from reflex.integrations.fakes.fake_browser import FakeBrowserPage
from reflex.ports.action import ActionPort
from reflex.ports.clock import DeterministicClock
from reflex.ports.observation import ObservationPort
from reflex.schemas.actions import ActionType, NormalizedCoords, SafetyClass, TypedAction
from reflex.schemas.delta import OutcomeClass, StateDelta
from reflex.schemas.identity import ActionIdentity, ActionProposal
from reflex.schemas.memory import MotorSkill, TransitionTuple
from reflex.schemas.state import BoundingBox, CanonicalUIGraph, NodeRole, UIStateNode


class RecordingActionPort(ActionPort):
    """Fake port WITHOUT a lease_manager attribute (mock pass-through)."""

    def __init__(self) -> None:
        self.dispatched: List[Tuple[TypedAction, ActionIdentity]] = []

    async def dispatch_action(
        self, action: TypedAction, identity: ActionIdentity
    ) -> Dict[str, Any]:
        self.dispatched.append((action, identity))
        return {"status": "dispatched", "action_id": identity.action_id}


class FixedObservationPort(ObservationPort):
    """Observation port replaying one fixed graph."""

    def __init__(self, graph: CanonicalUIGraph) -> None:
        self.graph = graph

    async def capture_state(self) -> CanonicalUIGraph:
        return self.graph

    async def capture_screenshot(self) -> bytes:
        return b""


def _graph(label: str) -> CanonicalUIGraph:
    return CanonicalUIGraph(
        timestamp_ms=1000.0,
        nodes={
            "btn": UIStateNode(
                node_id="btn",
                role=NodeRole.BUTTON,
                bounds=BoundingBox(10, 10, 100, 30),
                label=label,
            )
        },
        url="http://example.com/app",
    )


class TestKernelNativeBoundary(unittest.IsolatedAsyncioTestCase):
    """Condition 2: kernel-outbound native wirings fail closed with zero events."""

    def setUp(self):
        self.clock = DeterministicClock(start_time_ms=1000000.0)

    async def test_kernel_to_manager_free_native_fails_closed_zero_events(self):
        manager = ActionLeaseManager(clock=self.clock)
        substrate = MockLinuxInputSubstrate()
        adapter = LinuxNativeInputAdapter(substrate=substrate)  # lease_manager=None
        kernel = HostControlKernel(
            action_port=adapter, lease_manager=manager, clock=self.clock
        )
        proposal = ActionProposal(
            identity=ActionIdentity.create("gap2a", 1),
            action=TypedAction(
                action_type=ActionType.CLICK, coords=NormalizedCoords(0.5, 0.5)
            ),
        )
        result = await kernel.submit_proposal(proposal)
        self.assertEqual(result.state, DispatchState.RETIRED_FAILED)
        self.assertIn("not bound", result.error_message or "")
        self.assertEqual(len(substrate.events), 0)

    async def test_kernel_to_shared_manager_native_succeeds_two_events(self):
        # Post-C2-fix: native dispatch looks up the kernel-issued registered
        # lease, so legitimate kernel→native dispatch succeeds with exact events.
        manager = ActionLeaseManager(clock=self.clock)
        substrate = MockLinuxInputSubstrate()
        adapter = LinuxNativeInputAdapter(
            lease_manager=manager, substrate=substrate, clock=self.clock
        )
        kernel = HostControlKernel(
            action_port=adapter, lease_manager=manager, clock=self.clock
        )
        proposal = ActionProposal(
            identity=ActionIdentity.create("gap2b", 1),
            action=TypedAction(
                action_type=ActionType.CLICK, coords=NormalizedCoords(0.5, 0.5)
            ),
        )
        result = await kernel.submit_proposal(proposal)
        self.assertEqual(result.state, DispatchState.RETIRED_SUCCESS)
        self.assertEqual(len(substrate.events), 2)

    async def test_kernel_to_foreign_manager_cdp_refused_zero_events(self):
        kernel_manager = ActionLeaseManager(clock=self.clock)
        foreign_manager = ActionLeaseManager(clock=self.clock)
        page = FakeBrowserPage(viewport_width=1280, viewport_height=800)
        adapter = CDPActionAdapter(page=page, lease_manager=foreign_manager)
        kernel = HostControlKernel(
            action_port=adapter, lease_manager=kernel_manager, clock=self.clock
        )
        proposal = ActionProposal(
            identity=ActionIdentity.create("gap2c", 1),
            action=TypedAction(action_type=ActionType.CLICK, target_node_id="#x"),
        )
        result = await kernel.submit_proposal(proposal)
        self.assertEqual(result.state, DispatchState.RETIRED_FAILED)
        self.assertIn("not bound", result.error_message or "")
        self.assertEqual(len(page.event_log), 0)


class TestValueSwapClosure(unittest.IsolatedAsyncioTestCase):
    """Condition 3: divergent text_payload/value can never authorize or execute."""

    def setUp(self):
        self.clock = DeterministicClock(start_time_ms=1000000.0)

    def _divergent(self) -> TypedAction:
        return TypedAction(
            action_type=ActionType.TYPE,
            target_node_id="inp",
            text_payload="benign shown to approver",
            value="hostile string reaching substrate",
        )

    async def test_issuance_of_divergent_action_rejected(self):
        manager = ActionLeaseManager(clock=self.clock)
        with self.assertRaises(InvalidLeaseError):
            manager.issue_lease(ActionIdentity.create("gap3a", 1), self._divergent())

    async def test_empty_payload_with_hostile_value_rejected(self):
        # `text_payload or value` fallback would select the unsigned value.
        manager = ActionLeaseManager(clock=self.clock)
        action = TypedAction(
            action_type=ActionType.TYPE, text_payload="", value="hostile"
        )
        with self.assertRaises(InvalidLeaseError):
            manager.issue_lease(ActionIdentity.create("gap3b", 1), action)

    async def test_swap_between_issue_and_dispatch_rejected_zero_events(self):
        manager = ActionLeaseManager(clock=self.clock)
        page = FakeBrowserPage(viewport_width=1280, viewport_height=800)
        adapter = CDPActionAdapter(page=page, lease_manager=manager)
        clean = TypedAction(
            action_type=ActionType.TYPE, target_node_id="inp", text_payload="ok"
        )
        identity = ActionIdentity.create("gap3c", 1)
        lease = manager.issue_lease(identity, clean)
        swapped = TypedAction(
            action_type=ActionType.TYPE,
            target_node_id="inp",
            text_payload="ok",
            value="swapped",
        )
        with self.assertRaises(InvalidLeaseError):
            await adapter.execute_action(action=swapped, lease=lease)
        self.assertEqual(len(page.event_log), 0)

    async def test_divergent_action_through_kernel_zero_events(self):
        manager = ActionLeaseManager(clock=self.clock)
        substrate = MockLinuxInputSubstrate()
        adapter = LinuxNativeInputAdapter(
            lease_manager=manager, substrate=substrate, clock=self.clock
        )
        kernel = HostControlKernel(
            action_port=adapter, lease_manager=manager, clock=self.clock
        )
        proposal = ActionProposal(
            identity=ActionIdentity.create("gap3d", 1), action=self._divergent()
        )
        result = await kernel.submit_proposal(proposal)
        self.assertEqual(result.state, DispatchState.RETIRED_FAILED)
        self.assertEqual(len(substrate.events), 0)
        self.assertEqual(substrate.pressed_keys, [])


class TestKernelRoutedReplay(unittest.IsolatedAsyncioTestCase):
    """Condition 4: replay dispatch flows through the kernel, never leaseless."""

    def setUp(self):
        self.clock = DeterministicClock(start_time_ms=1000000.0)

    def _transition(self, action: TypedAction, post: CanonicalUIGraph) -> TransitionTuple:
        pre = _graph("before")
        return TransitionTuple(
            transition_id="tx_gap",
            episode_id="ep_gap",
            step_index=0,
            timestamp_ms=pre.timestamp_ms,
            ui_state_hash=pre.compute_state_hash(),
            goal_text="gap",
            goal_embedding=[0.1],
            visual_embedding=None,
            action=action,
            next_ui_state_hash=post.compute_state_hash(),
            delta=StateDelta(outcome_class=OutcomeClass.SUCCESS),
            duration_ms=1.0,
            surprise_score=0.0,
            provenance={},
        )

    async def test_replay_through_real_kernel_emits_exactly_one_event(self):
        post = _graph("after")
        page = FakeBrowserPage(viewport_width=1280, viewport_height=800)
        page.register_element("#go", tag_name="button", text="Go")
        manager = ActionLeaseManager(clock=self.clock)
        adapter = CDPActionAdapter(page=page, lease_manager=manager)
        kernel = HostControlKernel(
            action_port=adapter, lease_manager=manager, clock=self.clock
        )
        runner = EpisodeReplayRunner(
            observation_port=FixedObservationPort(post),
            action_port=adapter,
            clock=self.clock,
            kernel=kernel,
        )
        report = await runner.replay_episode(
            "ep_gap",
            transitions=[
                self._transition(
                    TypedAction(
                        action_type=ActionType.CLICK, target_node_id="#go"
                    ),
                    post,
                )
            ],
        )
        self.assertEqual(report.total_steps, 1)
        self.assertEqual(report.matched_steps, 1)
        clicks = [e for e in page.event_log if e.get("event") == "element_click"]
        self.assertEqual(len(clicks), 1)

    async def test_replay_halted_kernel_records_failure_zero_dispatch(self):
        port = RecordingActionPort()
        kernel = HostControlKernel(action_port=port, clock=self.clock)
        kernel.emergency_halt("gap halt")
        runner = EpisodeReplayRunner(
            observation_port=FixedObservationPort(_graph("after")),
            action_port=port,
            clock=self.clock,
            kernel=kernel,
        )
        report = await runner.replay_episode(
            "ep_gap",
            transitions=[
                self._transition(
                    TypedAction(action_type=ActionType.NOOP), _graph("after")
                )
            ],
        )
        self.assertEqual(report.total_steps, 1)
        self.assertEqual(report.matched_steps, 0)
        self.assertEqual(report.step_results[0].observed_state_hash, "DISPATCH_FAILED")
        self.assertEqual(len(port.dispatched), 0)


class TestKernelRoutedExecutor(unittest.IsolatedAsyncioTestCase):
    """Condition 4: skill execution dispatch flows through the kernel."""

    def _skill(self) -> MotorSkill:
        return MotorSkill(
            skill_id="gap_skill_001",
            version=1,
            preconditions_hash="gap",
            goal_embedding=[0.1],
            visual_context_embedding=[0.2],
            action_sequence=[
                TypedAction(action_type=ActionType.NOOP, safety_class=SafetyClass.REVERSIBLE)
            ],
            expected_delta=StateDelta(outcome_class=OutcomeClass.SUCCESS),
            timing_mean_ms=1.0,
            timing_std_ms=0.0,
            confidence=1.0,
            safety_class=SafetyClass.REVERSIBLE,
            provenance_episode_ids=[],
            validated_count=0,
        )

    async def test_execute_skill_routes_through_kernel(self):
        port = RecordingActionPort()
        kernel = HostControlKernel(action_port=port)
        executor = SkillReplayExecutor()
        result = await executor.execute_skill(
            skill=self._skill(),
            observation_port=FixedObservationPort(_graph("live")),
            action_port=port,
            kernel=kernel,
        )
        self.assertTrue(result.success)
        self.assertEqual(len(port.dispatched), 1)

    async def test_execute_skill_halted_kernel_fails_zero_dispatch(self):
        port = RecordingActionPort()
        kernel = HostControlKernel(action_port=port)
        kernel.emergency_halt("gap halt")
        executor = SkillReplayExecutor()
        result = await executor.execute_skill(
            skill=self._skill(),
            observation_port=FixedObservationPort(_graph("live")),
            action_port=port,
            kernel=kernel,
        )
        self.assertFalse(result.success)
        self.assertEqual(len(port.dispatched), 0)


class TestLeaseRegistryNegatives(unittest.IsolatedAsyncioTestCase):
    """Cross-instance and duplicate-issuance negatives for the new authority."""

    def setUp(self):
        self.clock = DeterministicClock(start_time_ms=1000000.0)

    async def test_cross_manager_lease_rejected(self):
        action = TypedAction(
            action_type=ActionType.CLICK, coords=NormalizedCoords(0.5, 0.5)
        )
        identity = ActionIdentity.create("gap5a", 1)
        lease = ActionLeaseManager(clock=self.clock).issue_lease(identity, action)
        other = ActionLeaseManager(clock=self.clock)
        with self.assertRaises(InvalidLeaseError):
            other.validate_lease(lease, action=action)

    async def test_duplicate_issuance_rejected(self):
        manager = ActionLeaseManager(clock=self.clock)
        action = TypedAction(
            action_type=ActionType.CLICK, coords=NormalizedCoords(0.5, 0.5)
        )
        identity = ActionIdentity.create("gap5b", 1)
        manager.issue_lease(identity, action)
        with self.assertRaises(InvalidLeaseError):
            manager.issue_lease(identity, action)


class TestDirectExecuteLeaseAuthority(unittest.IsolatedAsyncioTestCase):
    """Direct-execute authority pins: Mutant-B (local-fallback revert) killers.

    The manager-required validation half of the C2 fix rejects any
    manager-free native execution outright. A revert of
    ``NativeActionPort._validate_and_consume_lease`` to local-fallback
    validation goes GREEN on the pre-existing suite, so these pins exist:
    ``test_manager_free_direct_execute_rejected_zero_events`` MUST fail on
    such a revert (it would emit 2 substrate events instead of raising).
    """

    def setUp(self):
        self.clock = DeterministicClock(start_time_ms=1000000.0)

    def _click(self) -> TypedAction:
        return TypedAction(
            action_type=ActionType.CLICK, coords=NormalizedCoords(0.5, 0.5)
        )

    def _handmade_lease(self, tag: str, action: TypedAction) -> ActionLease:
        """Well-formed but unissued lease a local fallback would accept."""
        return ActionLease(
            lease_id=f"lease_handmade_{tag}",
            identity=ActionIdentity.create(tag, 1),
            action=action,
            expires_at_ms=9000000000000.0,
            created_at_ms=1000000.0,
            granted_at_ms=1000000.0,
        )

    async def test_manager_free_direct_execute_rejected_zero_events(self):
        # MUTANT-B KILLER: manager-free adapter + hand-made lease must raise
        # with 0 events. Local fallback would accept and emit exactly 2.
        substrate = MockLinuxInputSubstrate()
        adapter = LinuxNativeInputAdapter(
            lease_manager=None, substrate=substrate, clock=self.clock
        )
        action = self._click()
        handmade = self._handmade_lease("pinmgrfree", action)
        with self.assertRaises(InvalidLeaseError):
            await adapter.execute_action(action, handmade)
        self.assertEqual(len(substrate.events), 0)

    async def test_manager_bound_forged_lease_rejected_zero_events(self):
        # Unregistered/forged (tokenless, hand-made) lease against a bound
        # manager: rejected with 0 events. Passes on Mutant-B too (both
        # delegate to consume_lease); pins registered-authority requirement.
        manager = ActionLeaseManager(clock=self.clock)
        substrate = MockLinuxInputSubstrate()
        adapter = LinuxNativeInputAdapter(
            lease_manager=manager, substrate=substrate, clock=self.clock
        )
        action = self._click()
        forged = self._handmade_lease("pinforged", action)
        with self.assertRaises(InvalidLeaseError):
            await adapter.execute_action(action, forged)
        self.assertEqual(len(substrate.events), 0)

    async def test_manager_bound_foreign_lease_rejected_zero_events(self):
        # Valid token, wrong authority: lease issued by a foreign manager is
        # unregistered at the bound manager -> rejected with 0 events.
        foreign = ActionLeaseManager(clock=self.clock)
        manager = ActionLeaseManager(clock=self.clock)
        substrate = MockLinuxInputSubstrate()
        adapter = LinuxNativeInputAdapter(
            lease_manager=manager, substrate=substrate, clock=self.clock
        )
        action = self._click()
        identity = ActionIdentity.create("pinforeign", 1)
        foreign_lease = foreign.issue_lease(identity, action)
        with self.assertRaises(InvalidLeaseError):
            await adapter.execute_action(action, foreign_lease)
        self.assertEqual(len(substrate.events), 0)

    async def test_attributeless_port_still_dispatches_via_kernel(self):
        # CARVE-OUT BOUNDARY PIN (DELIBERATE H2 intended behavior): ports
        # WITHOUT a lease_manager attribute (test doubles, mock
        # pass-through) are exempt from the kernel's port-authority binding
        # check and still dispatch via the kernel. Only ports carrying the
        # attribute must share the kernel's manager instance.
        port = RecordingActionPort()
        kernel = HostControlKernel(action_port=port, clock=self.clock)
        proposal = ActionProposal(
            identity=ActionIdentity.create("pincarve", 1),
            action=self._click(),
        )
        result = await kernel.submit_proposal(proposal)
        self.assertEqual(result.state, DispatchState.RETIRED_SUCCESS)
        self.assertEqual(len(port.dispatched), 1)


if __name__ == "__main__":
    unittest.main()
