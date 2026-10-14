"""Typed exception hierarchy for the SST engine."""

from __future__ import annotations


class SSTError(Exception):
    """Base exception for all SST errors."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class PolicyViolationError(SSTError):
    """Raised when a search or scope policy is violated."""

    pass


class ScopeViolationError(PolicyViolationError):
    """Raised when a patch targets forbidden or unlisted paths."""

    pass


class SecurityViolationError(PolicyViolationError):
    """Raised when hardcoded secrets or malicious tokens are detected."""

    pass


class PathTraversalError(SecurityViolationError):
    """Raised when a path escapes the sandbox workspace root."""

    pass


class BudgetExhaustedError(SSTError):
    """Raised when resource budgets (tokens, cost, time, iterations) are exceeded."""

    pass


class UnpricedCostBudgetError(SSTError):
    """Raised when a USD cost cap is set but a response has no valid cost accounting."""

    pass


class CustodyError(SSTError):
    """Raised when candidate workspace isolation or patch application fails."""

    pass


class VerifierError(SSTError):
    """Raised when an automated verifier encounters an execution fault."""

    pass


class LeaseAcquisitionError(SSTError):
    """Raised when a guarded search run cannot acquire the tree writer lease."""

    pass


class IncompleteSearchError(SSTError):
    """Raised when no finished SEARCH_COMPLETED marker exists for a tree."""

    pass
