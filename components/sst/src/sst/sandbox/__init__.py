"""Sandboxed candidate custody, isolated worktrees, and deterministic gate evaluation."""

from .custody import CandidateCustodyManager, PatchApplicationResult
from .evaluator import SSTDeterministicEvaluator
from .executor import ExecutorUnavailableError, bind_executor, resolve_executor
from .outcomes import (
    LEGACY_OUTCOME_CARRIER_KIND,
    OUTCOME_CARRIER_KIND,
    OUTCOME_RECORD_TYPE,
    get_outcomes,
    is_outcome_event,
    report_outcome,
)

__all__ = [
    "CandidateCustodyManager",
    "PatchApplicationResult",
    "SSTDeterministicEvaluator",
    "ExecutorUnavailableError",
    "bind_executor",
    "resolve_executor",
    "LEGACY_OUTCOME_CARRIER_KIND",
    "OUTCOME_CARRIER_KIND",
    "OUTCOME_RECORD_TYPE",
    "get_outcomes",
    "is_outcome_event",
    "report_outcome",
]
