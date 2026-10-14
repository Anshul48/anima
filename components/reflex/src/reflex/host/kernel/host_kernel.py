from __future__ import annotations
from abc import ABC, abstractmethod
import asyncio
from dataclasses import dataclass, field
from enum import Enum
import inspect
import time
from typing import Any, Awaitable, Callable, Dict, List, Optional, Set, Tuple, Union

from reflex.host.identity.idempotency_registry import (
    IdempotencyCollisionError,
    IdempotencyRegistry,
    NonMonotonicStepError,
)
from reflex.host.identity.lease_manager import (
    ActionLease,
    ActionLeaseManager,
    InvalidLeaseError,
    LeaseAlreadyAcquiredError,
    LeaseError,
    LeaseExpiredError,
    LeaseRevokedError,
)
from reflex.host.policy.capability_engine import (
    CapabilityPolicyEngine,
    PolicyEvaluationResult,
)
from reflex.ports.action import ActionPort, ActionReceipt, ActionStatus
from reflex.ports.clock import ClockPort, SystemClock
from reflex.ports.observation import ObservationPort
from reflex.ports.verification import VerificationPort
from reflex.schemas.actions import TypedAction
from reflex.schemas.delta import OutcomeClass, StateDelta
from reflex.schemas.identity import ActionIdentity, ActionProposal
from reflex.schemas.policy import CapabilityPolicy
from reflex.schemas.state import CanonicalUIGraph


class DispatchState(str, Enum):
    IDLE = "idle"
    PROPOSAL_RECEIVED = "proposal_received"
    AUTHORIZING = "authorizing"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    LEASE_ISSUED = "lease_issued"
    IN_FLIGHT = "in_flight"
    SETTLING = "settling"
    VERIFYING = "verifying"
    RECONCILING = "reconciling"
    RETIRED_SUCCESS = "retired_success"
    RETIRED_FAILED = "retired_failed"


VALID_TRANSITIONS: Dict[DispatchState, Set[DispatchState]] = {
    DispatchState.IDLE: {
        DispatchState.PROPOSAL_RECEIVED,
    },
    DispatchState.PROPOSAL_RECEIVED: {
        DispatchState.AUTHORIZING,
        DispatchState.RETIRED_FAILED,
    },
    DispatchState.AUTHORIZING: {
        DispatchState.AWAITING_CONFIRMATION,
        DispatchState.LEASE_ISSUED,
        DispatchState.RETIRED_FAILED,
    },
    DispatchState.AWAITING_CONFIRMATION: {
        DispatchState.LEASE_ISSUED,
        DispatchState.RETIRED_FAILED,
    },
    DispatchState.LEASE_ISSUED: {
        DispatchState.IN_FLIGHT,
        DispatchState.RECONCILING,
        DispatchState.RETIRED_FAILED,
    },
    DispatchState.IN_FLIGHT: {
        DispatchState.SETTLING,
        DispatchState.RECONCILING,
        DispatchState.RETIRED_FAILED,
    },
    DispatchState.SETTLING: {
        DispatchState.VERIFYING,
        DispatchState.RECONCILING,
        DispatchState.RETIRED_FAILED,
    },
    DispatchState.VERIFYING: {
        DispatchState.RETIRED_SUCCESS,
        DispatchState.RECONCILING,
        DispatchState.RETIRED_FAILED,
    },
    DispatchState.RECONCILING: {
        DispatchState.RETIRED_FAILED,
    },
    DispatchState.RETIRED_SUCCESS: {
        DispatchState.IDLE,
        DispatchState.PROPOSAL_RECEIVED,
    },
    DispatchState.RETIRED_FAILED: {
        DispatchState.IDLE,
        DispatchState.PROPOSAL_RECEIVED,
    },
}


class KernelError(Exception):
    """Base exception for host control kernel errors."""
    pass


class EmergencyHaltError(KernelError):
    """Raised when an operation is attempted while the kernel is in emergency halt mode."""
    pass


class InvalidStateTransitionError(KernelError):
    """Raised when an illegal state transition is attempted in the dispatch state machine."""
    pass


class PolicyRejectedError(KernelError):
    """Raised when an action proposal fails policy authorization."""
    pass


class ConfirmationDeniedError(KernelError):
    """Raised when human confirmation is explicitly denied."""
    pass


class ConfirmationTimeoutError(KernelError):
    """Raised when human confirmation times out."""
    pass


class ExecutionTimeoutError(KernelError):
    """Raised when physical action dispatch exceeds execution timeout."""
    pass


class SettlementTimeoutError(KernelError):
    """Raised when post-action settlement exceeds maximum allowable timeout."""
    pass


class VerificationFailedError(KernelError):
    """Raised when post-action state verification fails."""
    pass


@dataclass(frozen=True)
class KernelDispatchResult:
    """Terminal outcome of a kernel dispatch attempt."""
    identity: ActionIdentity
    outcome: OutcomeClass
    execution_latency_ms: float
    verification_passed: bool
    requires_reconciliation: bool = False
    error_message: Optional[str] = None
    state: DispatchState = DispatchState.RETIRED_SUCCESS
    receipt: Optional[ActionReceipt] = None
    state_delta: Optional[StateDelta] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "identity": self.identity.to_dict(),
            "outcome": self.outcome.value if isinstance(self.outcome, OutcomeClass) else str(self.outcome),
            "execution_latency_ms": self.execution_latency_ms,
            "verification_passed": self.verification_passed,
            "requires_reconciliation": self.requires_reconciliation,
            "error_message": self.error_message,
            "state": self.state.value if isinstance(self.state, DispatchState) else str(self.state),
            "receipt": self.receipt.to_dict() if self.receipt else None,
            "state_delta": self.state_delta.to_dict() if self.state_delta else None,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> KernelDispatchResult:
        raw_outcome = data.get("outcome", OutcomeClass.SUCCESS.value)
        outcome = OutcomeClass(raw_outcome) if raw_outcome in OutcomeClass._value2member_map_ else OutcomeClass(raw_outcome.lower())
        raw_state = data.get("state", DispatchState.RETIRED_SUCCESS.value)
        state = DispatchState(raw_state) if raw_state in DispatchState._value2member_map_ else DispatchState(raw_state.lower())

        return cls(
            identity=ActionIdentity.from_dict(data["identity"]),
            outcome=outcome,
            execution_latency_ms=float(data.get("execution_latency_ms", 0.0)),
            verification_passed=bool(data.get("verification_passed", False)),
            requires_reconciliation=bool(data.get("requires_reconciliation", False)),
            error_message=data.get("error_message"),
            state=state,
            receipt=ActionReceipt.from_dict(data["receipt"]) if data.get("receipt") else None,
            state_delta=StateDelta.from_dict(data["state_delta"]) if data.get("state_delta") else None,
            metadata=data.get("metadata", {}),
        )


class HostControlKernelPort(ABC):
    """Abstract interface defining the Host-Local Control Kernel."""

    @abstractmethod
    async def submit_proposal(self, proposal: ActionProposal) -> KernelDispatchResult:
        """Processes an action proposal through authorization, dispatch, and verification."""
        ...

    @abstractmethod
    def emergency_halt(self, reason: str) -> None:
        """Immediately revokes active leases and halts all host execution."""
        ...


class HostControlKernel(HostControlKernelPort):
    """Host-Local Control Kernel acting as the sole action authority for Reflex."""

    def __init__(
        self,
        policy: Optional[CapabilityPolicy] = None,
        policy_engine: Optional[CapabilityPolicyEngine] = None,
        action_port: Optional[ActionPort] = None,
        observation_port: Optional[ObservationPort] = None,
        verification_port: Optional[VerificationPort] = None,
        clock: Optional[ClockPort] = None,
        lease_manager: Optional[ActionLeaseManager] = None,
        idempotency_registry: Optional[IdempotencyRegistry] = None,
        human_confirmation_callback: Optional[
            Union[Callable[[ActionProposal], Awaitable[bool]], Callable[[ActionProposal], bool]]
        ] = None,
        confirmation_timeout_s: float = 60.0,
        dispatch_timeout_s: float = 10.0,
        settle_timeout_s: float = 5.0,
        settle_interval_s: float = 0.05,
    ):
        self._clock: ClockPort = clock or SystemClock()
        self._policy = policy or CapabilityPolicy.default_browser_policy()
        self._policy_engine = policy_engine or CapabilityPolicyEngine(self._policy)
        self._action_port = action_port
        self._observation_port = observation_port
        self._verification_port = verification_port
        self._lease_manager = lease_manager or ActionLeaseManager(clock=self._clock)
        self._idempotency_registry = idempotency_registry or IdempotencyRegistry(clock=self._clock)
        self._human_confirmation_callback = human_confirmation_callback

        self.confirmation_timeout_s = confirmation_timeout_s
        self.dispatch_timeout_s = dispatch_timeout_s
        self.settle_timeout_s = settle_timeout_s
        self.settle_interval_s = settle_interval_s

        self._state: DispatchState = DispatchState.IDLE
        self._state_history: List[Tuple[DispatchState, DispatchState, float]] = []
        self._session_action_counts: Dict[str, int] = {}
        self._is_halted: bool = False
        self._halt_reason: str = ""
        self._active_dispatch_task: Optional[asyncio.Task] = None
        self._dispatch_lock = asyncio.Lock()

    @property
    def current_state(self) -> DispatchState:
        return self._state

    @property
    def is_halted(self) -> bool:
        return self._is_halted

    @property
    def halt_reason(self) -> str:
        return self._halt_reason

    @property
    def policy_engine(self) -> CapabilityPolicyEngine:
        return self._policy_engine

    @property
    def lease_manager(self) -> ActionLeaseManager:
        return self._lease_manager

    @property
    def idempotency_registry(self) -> IdempotencyRegistry:
        return self._idempotency_registry

    @property
    def state_history(self) -> List[Tuple[DispatchState, DispatchState, float]]:
        return list(self._state_history)

    def transition_to(self, new_state: DispatchState) -> None:
        """Transitions kernel to new state if permitted by valid state graph."""
        valid_next = VALID_TRANSITIONS.get(self._state, set())
        if new_state not in valid_next:
            raise InvalidStateTransitionError(
                f"Invalid state transition from '{self._state.value}' to '{new_state.value}'. Permitted transitions: {[s.value for s in valid_next]}"
            )
        old_state = self._state
        self._state = new_state
        now_ms = self._clock.now_ms()
        self._state_history.append((old_state, new_state, now_ms))

    def emergency_halt(self, reason: str = "Emergency halt requested") -> None:
        """Immediately halts kernel, revokes active leases, and cancels running dispatch."""
        self._is_halted = True
        self._halt_reason = reason

        # 1. Mass lease revocation
        self._lease_manager.revoke_all_leases(reason=f"Emergency halt: {reason}")

        # 2. Cancel in-flight task if executing
        if self._active_dispatch_task and not self._active_dispatch_task.done():
            self._active_dispatch_task.cancel()

        # 3. Transition to terminal state if in an active non-idle phase
        if self._state not in {DispatchState.IDLE, DispatchState.RETIRED_FAILED, DispatchState.RETIRED_SUCCESS}:
            try:
                if self._state != DispatchState.RECONCILING:
                    self.transition_to(DispatchState.RECONCILING)
                self.transition_to(DispatchState.RETIRED_FAILED)
                self.transition_to(DispatchState.IDLE)
            except InvalidStateTransitionError:
                self._state = DispatchState.IDLE

    def resume(self) -> None:
        """Clears emergency halt condition and resumes operational readiness."""
        self._is_halted = False
        self._halt_reason = ""
        self._state = DispatchState.IDLE

    def reset(self) -> None:
        """Resets kernel state, lease manager, and idempotency registry."""
        self._state = DispatchState.IDLE
        self._state_history.clear()
        self._session_action_counts.clear()
        self._is_halted = False
        self._halt_reason = ""
        self._active_dispatch_task = None
        self._lease_manager.clear()
        self._idempotency_registry.clear()

    async def submit_proposal(self, proposal: ActionProposal) -> KernelDispatchResult:
        """Authorizes, executes, and verifies an action proposal through the state machine.
        
        Guarantees:
        1. Sole action authority via host kernel.
        2. Monotonic step order and duplicate suppression.
        3. At-most-one physical dispatch attempt per ActionIdentity.
        4. Strict state machine transitions.
        """
        # Fast emergency halt check
        if self._is_halted:
            raise EmergencyHaltError(f"Host execution is halted: {self._halt_reason}")

        # 1. Acquire single-dispatch execution lock
        async with self._dispatch_lock:
            # Re-check halt status under lock
            if self._is_halted:
                raise EmergencyHaltError(f"Host execution is halted: {self._halt_reason}")

            start_time_ms = self._clock.monotonic_ms()
            active_lease: Optional[ActionLease] = None
            receipt: Optional[ActionReceipt] = None
            before_state: Optional[CanonicalUIGraph] = None
            delta: Optional[StateDelta] = None

            try:
                # 2. Transition IDLE -> PROPOSAL_RECEIVED
                self.transition_to(DispatchState.PROPOSAL_RECEIVED)

                # Register in Idempotency Registry (atomic check for duplicates & monotonic step)
                self._idempotency_registry.register_proposal(
                    identity=proposal.identity,
                    initial_state=DispatchState.PROPOSAL_RECEIVED.value,
                )

                # Monotonic session action count
                session_id = proposal.identity.session_id
                current_action_count = self._session_action_counts.get(session_id, 0)

                # 3. Transition PROPOSAL_RECEIVED -> AUTHORIZING
                self.transition_to(DispatchState.AUTHORIZING)
                self._idempotency_registry.update_state(
                    proposal.identity.action_id,
                    new_state=DispatchState.AUTHORIZING.value,
                )

                eval_result = self._policy_engine.evaluate(
                    proposal=proposal,
                    session_action_count=current_action_count,
                    current_time_ms=self._clock.now_ms(),
                )

                # 4. Check Policy Authorization / Human Confirmation Gates
                if not eval_result.allowed:
                    if eval_result.requires_human_confirmation:
                        # Transition AUTHORIZING -> AWAITING_CONFIRMATION
                        self.transition_to(DispatchState.AWAITING_CONFIRMATION)
                        self._idempotency_registry.update_state(
                            proposal.identity.action_id,
                            new_state=DispatchState.AWAITING_CONFIRMATION.value,
                        )

                        confirmed = await self._handle_human_confirmation(proposal)
                        if not confirmed:
                            self.transition_to(DispatchState.RETIRED_FAILED)
                            self._idempotency_registry.record_terminal_result(
                                proposal.identity.action_id,
                                terminal_state=DispatchState.RETIRED_FAILED.value,
                                error="Human confirmation denied or timed out",
                            )
                            return KernelDispatchResult(
                                identity=proposal.identity,
                                outcome=OutcomeClass.ERROR,
                                execution_latency_ms=self._clock.monotonic_ms() - start_time_ms,
                                verification_passed=False,
                                requires_reconciliation=False,
                                error_message="Human confirmation denied or timed out",
                                state=DispatchState.RETIRED_FAILED,
                            )
                        # Confirmed: proceed to LEASE_ISSUED
                    else:
                        # Policy rejected (Scope, Domain, Rate Limit)
                        self.transition_to(DispatchState.RETIRED_FAILED)
                        self._idempotency_registry.record_terminal_result(
                            proposal.identity.action_id,
                            terminal_state=DispatchState.RETIRED_FAILED.value,
                            error=f"Policy rejected: {eval_result.reason}",
                        )
                        return KernelDispatchResult(
                            identity=proposal.identity,
                            outcome=OutcomeClass.ERROR,
                            execution_latency_ms=self._clock.monotonic_ms() - start_time_ms,
                            verification_passed=False,
                            requires_reconciliation=False,
                            error_message=f"Policy rejected: {eval_result.reason}",
                            state=DispatchState.RETIRED_FAILED,
                        )

                # Increment session count upon authorization
                self._session_action_counts[session_id] = current_action_count + 1

                # 5. Transition -> LEASE_ISSUED
                self.transition_to(DispatchState.LEASE_ISSUED)
                self._idempotency_registry.update_state(
                    proposal.identity.action_id,
                    new_state=DispatchState.LEASE_ISSUED.value,
                )

                active_lease = self._lease_manager.issue_lease(
                    identity=proposal.identity,
                    action=proposal.action,
                    ttl_ms=self.dispatch_timeout_s * 1000.0,
                )

                # Capture pre-action state if observation port available
                before_state: Optional[CanonicalUIGraph] = None
                if self._observation_port is not None:
                    try:
                        before_state = await self._observation_port.capture_state()
                    except Exception:
                        before_state = None

                # 6. Physical Dispatch -> IN_FLIGHT
                self.transition_to(DispatchState.IN_FLIGHT)
                # The adapter atomically consumes the actual issued lease at dispatch.
                self._idempotency_registry.atomic_begin_dispatch(proposal.identity.action_id)

                # Execute dispatch against adapter
                receipt = await self._execute_physical_dispatch(proposal, active_lease)

                # 7. Settlement -> SETTLING
                self.transition_to(DispatchState.SETTLING)
                self._idempotency_registry.update_state(
                    proposal.identity.action_id,
                    new_state=DispatchState.SETTLING.value,
                )

                settled = await self._await_settlement()
                if not settled:
                    # Settlement timeout reached -> effect unknown -> RECONCILING
                    self.transition_to(DispatchState.RECONCILING)
                    self.transition_to(DispatchState.RETIRED_FAILED)
                    self._idempotency_registry.record_terminal_result(
                        proposal.identity.action_id,
                        terminal_state=DispatchState.RETIRED_FAILED.value,
                        error="Settlement timeout reached",
                    )
                    return KernelDispatchResult(
                        identity=proposal.identity,
                        outcome=OutcomeClass.UNKNOWN_EFFECT,
                        execution_latency_ms=self._clock.monotonic_ms() - start_time_ms,
                        verification_passed=False,
                        requires_reconciliation=True,
                        error_message="Settlement timeout reached; transition effect unknown",
                        state=DispatchState.RETIRED_FAILED,
                        receipt=receipt,
                    )

                # 8. Post-Action Verification -> VERIFYING
                self.transition_to(DispatchState.VERIFYING)
                self._idempotency_registry.update_state(
                    proposal.identity.action_id,
                    new_state=DispatchState.VERIFYING.value,
                )

                verif_passed, delta = await self._perform_verification(
                    proposal=proposal,
                    before_state=before_state,
                )

                if verif_passed:
                    # Verification Succeeded -> RETIRED_SUCCESS
                    self._lease_manager.retire_lease(active_lease.lease_id)
                    self.transition_to(DispatchState.RETIRED_SUCCESS)
                    self._idempotency_registry.record_terminal_result(
                        proposal.identity.action_id,
                        terminal_state=DispatchState.RETIRED_SUCCESS.value,
                    )
                    outcome = delta.outcome_class if delta else OutcomeClass.SUCCESS
                    return KernelDispatchResult(
                        identity=proposal.identity,
                        outcome=outcome,
                        execution_latency_ms=self._clock.monotonic_ms() - start_time_ms,
                        verification_passed=True,
                        requires_reconciliation=False,
                        state=DispatchState.RETIRED_SUCCESS,
                        receipt=receipt,
                        state_delta=delta,
                    )
                else:
                    # Verification Failed -> RECONCILING -> RETIRED_FAILED
                    self.transition_to(DispatchState.RECONCILING)
                    self.transition_to(DispatchState.RETIRED_FAILED)
                    outcome = delta.outcome_class if delta else OutcomeClass.ERROR
                    self._idempotency_registry.record_terminal_result(
                        proposal.identity.action_id,
                        terminal_state=DispatchState.RETIRED_FAILED.value,
                        error=f"Verification failed with outcome: {outcome.value}",
                    )
                    return KernelDispatchResult(
                        identity=proposal.identity,
                        outcome=outcome,
                        execution_latency_ms=self._clock.monotonic_ms() - start_time_ms,
                        verification_passed=False,
                        requires_reconciliation=True,
                        error_message=f"Verification failed; outcome classified as '{outcome.value}'",
                        state=DispatchState.RETIRED_FAILED,
                        receipt=receipt,
                        state_delta=delta,
                    )

            except (asyncio.TimeoutError, TimeoutError, ExecutionTimeoutError) as te:
                if active_lease:
                    self._lease_manager.revoke_lease(active_lease.lease_id, reason=f"Execution timeout: {te}")
                if self._state in {DispatchState.IN_FLIGHT, DispatchState.SETTLING, DispatchState.VERIFYING}:
                    self.transition_to(DispatchState.RECONCILING)
                    self.transition_to(DispatchState.RETIRED_FAILED)
                elif self._state not in {DispatchState.IDLE, DispatchState.RETIRED_FAILED}:
                    self.transition_to(DispatchState.RETIRED_FAILED)

                self._idempotency_registry.record_terminal_result(
                    proposal.identity.action_id,
                    terminal_state=DispatchState.RETIRED_FAILED.value,
                    error=f"Action execution timed out: {te}",
                )
                return KernelDispatchResult(
                    identity=proposal.identity,
                    outcome=OutcomeClass.UNKNOWN_EFFECT,
                    execution_latency_ms=self._clock.monotonic_ms() - start_time_ms,
                    verification_passed=False,
                    requires_reconciliation=True,
                    error_message=f"Action dispatch timed out: {te}",
                    state=DispatchState.RETIRED_FAILED,
                )

            except (IdempotencyCollisionError, NonMonotonicStepError):
                # Propagate idempotency and monotonic step errors directly for rejection
                if self._state not in {DispatchState.IDLE, DispatchState.RETIRED_FAILED}:
                    self._state = DispatchState.IDLE
                raise

            except Exception as ex:
                if active_lease:
                    self._lease_manager.revoke_lease(active_lease.lease_id, reason=f"Kernel error: {ex}")
                if self._state in {DispatchState.IN_FLIGHT, DispatchState.SETTLING, DispatchState.VERIFYING}:
                    self.transition_to(DispatchState.RECONCILING)
                    self.transition_to(DispatchState.RETIRED_FAILED)
                elif self._state not in {DispatchState.IDLE, DispatchState.RETIRED_FAILED}:
                    self.transition_to(DispatchState.RETIRED_FAILED)

                self._idempotency_registry.record_terminal_result(
                    proposal.identity.action_id,
                    terminal_state=DispatchState.RETIRED_FAILED.value,
                    error=str(ex),
                )
                return KernelDispatchResult(
                    identity=proposal.identity,
                    outcome=OutcomeClass.UNKNOWN_EFFECT,
                    execution_latency_ms=self._clock.monotonic_ms() - start_time_ms,
                    verification_passed=False,
                    requires_reconciliation=True,
                    error_message=f"Dispatch error: {ex}",
                    state=DispatchState.RETIRED_FAILED,
                )

            finally:
                # Always reset back to IDLE from terminal states
                if self._state in {DispatchState.RETIRED_SUCCESS, DispatchState.RETIRED_FAILED}:
                    self.transition_to(DispatchState.IDLE)
                elif self._state != DispatchState.IDLE:
                    self._state = DispatchState.IDLE

    async def _handle_human_confirmation(self, proposal: ActionProposal) -> bool:
        """Awaits explicit human confirmation if confirmation callback is registered."""
        if not self._human_confirmation_callback:
            return False

        try:
            res = self._human_confirmation_callback(proposal)
            if inspect.isawaitable(res):
                confirmed = await asyncio.wait_for(res, timeout=self.confirmation_timeout_s)
            else:
                confirmed = bool(res)
            return bool(confirmed)
        except (asyncio.TimeoutError, TimeoutError):
            return False
        except Exception:
            return False

    def _require_port_authority_binding(self) -> None:
        """Refuses dispatch through real adapters not bound to this kernel's authority.

        Ports carrying a `lease_manager` attribute (all shipped CDP / synthetic /
        native adapters and the execution router) must share THIS kernel's
        ActionLeaseManager instance. Otherwise the kernel-issued lease could
        neither be resolved nor consumed at the adapter, and manager-free native
        ports would execute with no authority check at all. Ports without the
        attribute (test doubles, mock pass-through) are unaffected.
        """
        port = self._action_port
        if not hasattr(port, "lease_manager"):
            return
        if port.lease_manager is not self._lease_manager:
            raise InvalidLeaseError(
                "ActionPort is not bound to this kernel's issuing ActionLeaseManager"
            )

    async def _execute_physical_dispatch(
        self,
        proposal: ActionProposal,
        lease: ActionLease,
    ) -> ActionReceipt:
        """Dispatches authorized action to ActionPort adapter with timeout guards."""
        start_mono = self._clock.monotonic_ms()

        if self._action_port is not None:
            self._require_port_authority_binding()
            coro = self._action_port.dispatch_action(proposal.action, proposal.identity)
            self._active_dispatch_task = asyncio.create_task(coro)
            try:
                raw_response = await asyncio.wait_for(
                    asyncio.shield(self._active_dispatch_task),
                    timeout=self.dispatch_timeout_s,
                )
            finally:
                self._active_dispatch_task = None

            duration_ms = self._clock.monotonic_ms() - start_mono
            adapter_name = getattr(self._action_port, "adapter_name", "action_adapter")
            raw_dict = raw_response if isinstance(raw_response, dict) else {"response": raw_response}

            return ActionReceipt(
                lease_id=lease.lease_id,
                action_id=proposal.identity.action_id,
                adapter_name=adapter_name,
                dispatch_timestamp_ms=self._clock.now_ms(),
                duration_ms=duration_ms,
                raw_adapter_response=raw_dict,
                status=ActionStatus.DISPATCHED,
            )
        else:
            # Fake/no-op adapter pass-through
            duration_ms = self._clock.monotonic_ms() - start_mono
            return ActionReceipt(
                lease_id=lease.lease_id,
                action_id=proposal.identity.action_id,
                adapter_name="kernel_mock_adapter",
                dispatch_timestamp_ms=self._clock.now_ms(),
                duration_ms=duration_ms,
                raw_adapter_response={"mock": True},
                status=ActionStatus.DISPATCHED,
            )

    async def _await_settlement(self) -> bool:
        """Awaits post-action settlement quiet period."""
        if self.settle_interval_s > 0:
            await self._clock.sleep(self.settle_interval_s)
        return True

    async def _perform_verification(
        self,
        proposal: ActionProposal,
        before_state: Optional[CanonicalUIGraph],
    ) -> Tuple[bool, Optional[StateDelta]]:
        """Verifies state transition against VerificationPort."""
        if self._verification_port is None:
            # If no verifier configured, default to optimistic success
            return True, None

        if self._observation_port is not None:
            try:
                after_state = await self._observation_port.capture_state()
            except Exception:
                after_state = None
        else:
            after_state = None

        # Fallback dummy graphs if observations absent
        b_state = before_state or CanonicalUIGraph(timestamp_ms=self._clock.now_ms(), nodes={})
        a_state = after_state or CanonicalUIGraph(timestamp_ms=self._clock.now_ms(), nodes={})

        delta = await self._verification_port.verify_transition(
            before_state=b_state,
            action=proposal.action,
            after_state=a_state,
            expected_delta=proposal.expected_delta,
        )

        passed = delta.outcome_class in (
            OutcomeClass.SUCCESS,
            OutcomeClass.NAVIGATION,
        ) or (
            proposal.expected_delta is not None
            and delta.outcome_class == proposal.expected_delta.outcome_class
        )
        return passed, delta
