"""Standardized exception hierarchy for the STC engine."""


class STCError(Exception):
    """Base exception for all errors raised within the STC engine."""


class SpecIngestionError(STCError):
    """Raised when a specification cannot be parsed or validated."""


class AmbiguityThresholdExceededError(STCError):
    """Raised when specification ambiguity exceeds the threshold and requires Sovereign choice."""


class ContextBudgetExceededError(STCError):
    """Raised when a compiled task bundle exceeds the 25KB ceiling."""


class BundleSizeExceededError(ContextBudgetExceededError):
    """Raised when a task bundle exceeds the strict 25,600 byte ceiling."""


class TraceMemoryError(STCError):
    """Raised when an error occurs while querying the Project Trace cognitive memory store."""


class WorktreeError(STCError):
    """Base exception for Git worktree management failures."""


class WorktreeLeaseActiveError(WorktreeError):
    """Raised when attempting to lease an already active worktree."""


class SubstrateGateFailureError(STCError):
    """Raised when one or more mechanical substrate gates fail (ruff, mypy, pytest)."""


class ReceiptTamperingError(STCError):
    """Raised when a machine receipt fails cryptographic signature verification."""


class JudiciaryRejectionError(STCError):
    """Raised when the blind judiciary auditor rejects a candidate diff."""


class MaxEpochExceededError(STCError):
    """Raised when task retry attempts exceed the maximum allowable epochs."""
