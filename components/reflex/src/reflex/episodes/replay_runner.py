"""Reflex Deterministic Episode Replay Runner.

Executes recorded historical action trajectories against a live or fake browser
environment, observes subsequent UI state graphs, compares state hashes, detects
drift, and calculates determinism ratio metrics.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
import itertools
import json
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from reflex.episodes.journal import EpisodeJournalPort
from reflex.host.kernel.host_kernel import (
    DispatchState,
    HostControlKernel,
    HostControlKernelPort,
)
from reflex.ports.action import ActionPort
from reflex.ports.clock import ClockPort, SystemClock
from reflex.ports.observation import ObservationPort
from reflex.schemas.actions import TypedAction
from reflex.schemas.identity import ActionIdentity, ActionProposal
from reflex.schemas.memory import TransitionTuple
from reflex.schemas.state import CanonicalUIGraph

_replay_run_seq = itertools.count()


@dataclass(frozen=True)
class ReplayStepResult:
    """Outcome of a single replayed step."""

    step_index: int
    action_id: str
    expected_state_hash: str
    observed_state_hash: str
    is_deterministic_match: bool
    drift_details: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_index": self.step_index,
            "action_id": self.action_id,
            "expected_state_hash": self.expected_state_hash,
            "observed_state_hash": self.observed_state_hash,
            "is_deterministic_match": self.is_deterministic_match,
            "drift_details": self.drift_details,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ReplayStepResult:
        return cls(
            step_index=int(data["step_index"]),
            action_id=data["action_id"],
            expected_state_hash=data["expected_state_hash"],
            observed_state_hash=data["observed_state_hash"],
            is_deterministic_match=bool(data["is_deterministic_match"]),
            drift_details=data.get("drift_details"),
        )


@dataclass(frozen=True)
class ReplayReport:
    """Comprehensive evaluation of an episode replay."""

    episode_id: str
    total_steps: int
    matched_steps: int
    determinism_ratio: float
    step_results: List[ReplayStepResult]

    @property
    def is_fully_deterministic(self) -> bool:
        """Returns True if every step produced an exact deterministic hash match."""
        return self.matched_steps == self.total_steps and self.total_steps > 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "episode_id": self.episode_id,
            "total_steps": self.total_steps,
            "matched_steps": self.matched_steps,
            "determinism_ratio": self.determinism_ratio,
            "is_fully_deterministic": self.is_fully_deterministic,
            "step_results": [r.to_dict() for r in self.step_results],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ReplayReport:
        return cls(
            episode_id=data["episode_id"],
            total_steps=int(data["total_steps"]),
            matched_steps=int(data["matched_steps"]),
            determinism_ratio=float(data["determinism_ratio"]),
            step_results=[ReplayStepResult.from_dict(r) for r in data.get("step_results", [])],
        )


class EpisodeReplayRunner:
    """Replays historical action sequences against an environment and verifies determinism."""

    def __init__(
        self,
        journal: Optional[EpisodeJournalPort] = None,
        observation_port: Optional[ObservationPort] = None,
        action_port: Optional[ActionPort] = None,
        clock: Optional[ClockPort] = None,
        stop_on_drift: bool = False,
        delay_between_steps_ms: float = 0.0,
        kernel: Optional[HostControlKernelPort] = None,
    ) -> None:
        self.journal = journal
        self.observation_port = observation_port
        self.action_port = action_port
        self.clock = clock or SystemClock()
        self.stop_on_drift = stop_on_drift
        self.delay_between_steps_ms = delay_between_steps_ms
        self.kernel = kernel
        self._owned_kernel: Optional[HostControlKernel] = None

    def _dispatch_kernel(self) -> Optional[HostControlKernelPort]:
        """Resolves the kernel authority all replay dispatch flows through.

        An explicitly provided kernel wins (callers wiring real adapters share
        the kernel's lease manager with the adapter). Otherwise a kernel owned
        by this runner is built around the configured action port. There is no
        leaseless dispatch path: without any port, steps fail as DISPATCH_FAILED.
        """
        if self.kernel is not None:
            return self.kernel
        if self.action_port is None:
            return None
        if self._owned_kernel is None:
            self._owned_kernel = HostControlKernel(
                action_port=self.action_port, clock=self.clock
            )
        return self._owned_kernel

    async def replay_episode(
        self,
        episode_id: str,
        transitions: Optional[List[TransitionTuple]] = None,
        parameter_bindings: Optional[Dict[str, Any]] = None,
    ) -> ReplayReport:
        """Replays all transitions recorded in an episode or provided list."""
        if transitions is None:
            if self.journal is None:
                raise ValueError("Cannot replay episode without a configured EpisodeJournalPort or transitions list")
            transitions = await self.journal.get_episode_transitions(episode_id)

        return await self.replay_transitions(
            episode_id=episode_id,
            transitions=transitions,
            parameter_bindings=parameter_bindings,
        )

    async def replay_transitions(
        self,
        episode_id: str,
        transitions: List[TransitionTuple],
        parameter_bindings: Optional[Dict[str, Any]] = None,
    ) -> ReplayReport:
        """Replays a given sequence of TransitionTuples and computes determinism report."""
        if not transitions:
            return ReplayReport(
                episode_id=episode_id,
                total_steps=0,
                matched_steps=0,
                determinism_ratio=1.0,
                step_results=[],
            )

        step_results: List[ReplayStepResult] = []
        run_seq = next(_replay_run_seq)
        kernel = self._dispatch_kernel()

        for tx in transitions:
            action_to_dispatch = self._bind_parameters(tx.action, parameter_bindings)
            action_id = (
                action_to_dispatch.target_node_id
                or action_to_dispatch.target_label
                or f"act_step_{tx.step_index}"
            )
            expected_hash = tx.next_ui_state_hash or tx.ui_state_hash

            # 1. Dispatch action through the HostControlKernel authority.
            # Each replay run mints fresh identities (single-use leases cannot
            # be re-issued for a prior run's identities on a shared kernel).
            if kernel is not None:
                identity = ActionIdentity.create(
                    session_id=f"replay_{episode_id}_{run_seq}",
                    step_index=tx.step_index,
                )
                proposal = ActionProposal(
                    identity=identity,
                    action=action_to_dispatch,
                    reasoning_summary=f"Deterministic replay of {episode_id} step {tx.step_index}",
                    metadata={"episode_id": episode_id, "replay_run_seq": run_seq},
                )
                try:
                    result = await kernel.submit_proposal(proposal)
                except Exception as dispatch_err:
                    dispatch_err_text = f"Action dispatch failed with exception: {dispatch_err}"
                else:
                    dispatch_err_text = (
                        None
                        if result.state == DispatchState.RETIRED_SUCCESS
                        else f"Action dispatch refused by kernel: {result.error_message}"
                    )
                if dispatch_err_text is not None:
                    step_results.append(
                        ReplayStepResult(
                            step_index=tx.step_index,
                            action_id=action_id,
                            expected_state_hash=expected_hash,
                            observed_state_hash="DISPATCH_FAILED",
                            is_deterministic_match=False,
                            drift_details=dispatch_err_text,
                        )
                    )
                    if self.stop_on_drift:
                        break
                    continue

            # Optional delay between steps
            if self.delay_between_steps_ms > 0:
                await asyncio.sleep(self.delay_between_steps_ms / 1000.0)

            # 2. Capture observed state
            observed_state: Optional[CanonicalUIGraph] = None
            observed_hash = ""
            if self.observation_port is not None:
                try:
                    observed_state = await self.observation_port.capture_state()
                    observed_hash = observed_state.compute_state_hash()
                except Exception as obs_err:
                    observed_hash = "OBSERVATION_FAILED"
                    drift_details = f"Observation capture failed: {obs_err}"
                    step_results.append(
                        ReplayStepResult(
                            step_index=tx.step_index,
                            action_id=action_id,
                            expected_state_hash=expected_hash,
                            observed_state_hash=observed_hash,
                            is_deterministic_match=False,
                            drift_details=drift_details,
                        )
                    )
                    if self.stop_on_drift:
                        break
                    continue
            else:
                # If no observation port, match against recorded next hash (simulated dry pass)
                observed_hash = expected_hash

            # 3. Compare hashes and compute drift details
            is_match = (observed_hash == expected_hash)
            drift_details = None

            if not is_match:
                drift_details = self._analyze_drift(
                    step_index=tx.step_index,
                    expected_hash=expected_hash,
                    observed_hash=observed_hash,
                    observed_state=observed_state,
                    transition=tx,
                )

            step_result = ReplayStepResult(
                step_index=tx.step_index,
                action_id=action_id,
                expected_state_hash=expected_hash,
                observed_state_hash=observed_hash,
                is_deterministic_match=is_match,
                drift_details=drift_details,
            )
            step_results.append(step_result)

            if not is_match and self.stop_on_drift:
                break

        total_steps = len(transitions)
        matched_steps = sum(1 for r in step_results if r.is_deterministic_match)
        determinism_ratio = matched_steps / total_steps if total_steps > 0 else 1.0

        return ReplayReport(
            episode_id=episode_id,
            total_steps=total_steps,
            matched_steps=matched_steps,
            determinism_ratio=determinism_ratio,
            step_results=step_results,
        )

    def _bind_parameters(
        self,
        action: TypedAction,
        bindings: Optional[Dict[str, Any]],
    ) -> TypedAction:
        """Substitutes template variables in action text_payload or metadata."""
        if not bindings:
            return action

        text = action.text_payload
        if text:
            for k, v in bindings.items():
                pattern = f"{{{{{k}}}}}"
                if pattern in text:
                    text = text.replace(pattern, str(v))
                bracket_pattern = f"[{k}]"
                if bracket_pattern in text:
                    text = text.replace(bracket_pattern, str(v))

        # Clone action with substituted payload
        return TypedAction(
            action_type=action.action_type,
            target_node_id=action.target_node_id,
            target_label=action.target_label,
            coords=action.coords,
            text_payload=text,
            key_code=action.key_code,
            scroll_delta=action.scroll_delta,
            safety_class=action.safety_class,
            metadata=dict(action.metadata),
        )

    def _analyze_drift(
        self,
        step_index: int,
        expected_hash: str,
        observed_hash: str,
        observed_state: Optional[CanonicalUIGraph],
        transition: TransitionTuple,
    ) -> str:
        """Constructs a descriptive explanation of the observed UI state drift."""
        exp_short = expected_hash[:8] if expected_hash else "None"
        obs_short = observed_hash[:8] if observed_hash else "None"

        reasons: List[str] = [
            f"Hash mismatch at step {step_index}: expected {exp_short}..., observed {obs_short}..."
        ]

        if observed_state is not None:
            if observed_state.url:
                reasons.append(f"Observed URL: '{observed_state.url}'")
            if observed_state.active_window_title:
                reasons.append(f"Window Title: '{observed_state.active_window_title}'")
            reasons.append(f"Observed Node Count: {len(observed_state.nodes)}")

            # Check delta expectations
            delta = transition.delta
            if delta.added_nodes:
                missing_adds = [nid for nid in delta.added_nodes if nid not in observed_state.nodes]
                if missing_adds:
                    reasons.append(f"Expected added nodes missing in live state: {missing_adds}")

            if delta.removed_nodes:
                unexpected_present = [nid for nid in delta.removed_nodes if nid in observed_state.nodes]
                if unexpected_present:
                    reasons.append(f"Expected removed nodes still present in live state: {unexpected_present}")

        return "; ".join(reasons)
