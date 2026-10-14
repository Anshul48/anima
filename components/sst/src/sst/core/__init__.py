"""Core models, contracts, events, and error hierarchies for SST."""

from .contracts import (
    CandidateProposal,
    HumanDecisionRecord,
    ScoreBreakdown,
    TaskPacket,
)
from .errors import (
    BudgetExhaustedError,
    CustodyError,
    PathTraversalError,
    PolicyViolationError,
    ScopeViolationError,
    SecurityViolationError,
    SSTError,
    VerifierError,
)
from .events import EventKind, SSTEvent
from .models import (
    AuDHDContextCapsule,
    ContextCapsule,
    CortexEvaluation,
    DeterministicGateResult,
    DomainMode,
    NodeRole,
    NodeStatus,
    PayloadType,
    SSTNode,
    SSTTree,
)

__all__ = [
    "DomainMode",
    "NodeRole",
    "NodeStatus",
    "PayloadType",
    "AuDHDContextCapsule",
    "ContextCapsule",
    "DeterministicGateResult",
    "CortexEvaluation",
    "SSTNode",
    "SSTTree",
    "TaskPacket",
    "CandidateProposal",
    "ScoreBreakdown",
    "HumanDecisionRecord",
    "EventKind",
    "SSTEvent",
    "SSTError",
    "PolicyViolationError",
    "ScopeViolationError",
    "SecurityViolationError",
    "PathTraversalError",
    "BudgetExhaustedError",
    "CustodyError",
    "VerifierError",
]
