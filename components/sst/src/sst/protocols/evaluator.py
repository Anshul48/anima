"""PEP 544 Protocol for deterministic evaluation gates."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from sst.core.models import DeterministicGateResult, SSTNode


@runtime_checkable
class EvaluatorProtocol(Protocol):
    """Protocol defining deterministic sandbox evaluation gatekeepers."""

    def evaluate(
        self,
        node: SSTNode,
        workspace_dir: Path | str,
        test_command: str | None = None,
        baseline_metrics: dict[str, float] | None = None,
    ) -> DeterministicGateResult:
        """Evaluates an SST node through deterministic gates."""
        ...
