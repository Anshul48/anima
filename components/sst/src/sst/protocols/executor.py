"""PEP 544 Protocol for injectable SST candidate executors.

The executor seam decouples the search controller from the concrete sandbox
implementation. Any object satisfying :class:`ExecutorProtocol` can execute
candidates: the default :class:`CandidateCustodyManager`, a test fake, or a
remote-execution backend.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, ClassVar, Protocol, runtime_checkable

from sst.core.contracts import CandidateProposal, TaskPacket
from sst.core.models import DeterministicGateResult

if TYPE_CHECKING:
    from sst.sandbox.custody import PatchApplicationResult

EXECUTOR_PROTOCOL_VERSION: str = "executor/v1"


@runtime_checkable
class ExecutorProtocol(Protocol):
    """Protocol defining candidate patch application and acceptance execution.

    Timeout / failure semantics (binding on all implementations):

    - Domain failures are *returned*, never raised: patch-application
      failures surface as ``PatchApplicationResult(success=False, ...)`` and
      acceptance failures (including timeouts) surface as
      ``DeterministicGateResult(passed=False, ...)``.
    - Acceptance timeout: ``passed=False``, ``exit_code=124``,
      ``failure_reason`` names the timeout, and ``duration_seconds``
      reflects the enforced timeout.
    - Patch-application failure inside an acceptance run: ``passed=False``,
      ``exit_code=1``, with the apply error in ``stderr``/``failure_reason``.
    - Only programming errors (wrong types, missing workspace root, etc.)
      may raise; operational failures must be encoded in the result.
    """

    executor_version: ClassVar[str]

    def apply_proposal(
        self,
        proposal: CandidateProposal,
        workspace_dir: Path | str,
        task: TaskPacket | None = None,
    ) -> PatchApplicationResult:
        """Applies a candidate proposal to an isolated workspace."""
        ...

    def verify_candidate_proposal(
        self,
        task: TaskPacket,
        proposal: CandidateProposal,
        source_dir: Path | str,
        acceptance_command: str | None = None,
        timeout: int = 120,
    ) -> DeterministicGateResult:
        """Applies a proposal and runs the acceptance gate, returning the verdict."""
        ...
