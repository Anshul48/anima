"""State Space Tree (SST) Asymmetric Dialectic MCTS Search Engine."""

from __future__ import annotations

from sst.cli.runner import SSTBuildRunner
from sst.context.capsule import ContextCapsuleCompiler
from sst.context.provider import ArchitectureEvidence, ContextProvider
from sst.core.contracts import (
    CandidateProposal,
    HumanDecisionRecord,
    ScoreBreakdown,
    TaskPacket,
)
from sst.core.errors import (
    BudgetExhaustedError,
    CustodyError,
    PathTraversalError,
    PolicyViolationError,
    ScopeViolationError,
    SecurityViolationError,
    SSTError,
    VerifierError,
)
from sst.core.events import EventKind, SSTEvent
from sst.core.models import (
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
from sst.gateway.backends import SSTLLMClient
from sst.gateway.contracts import (
    AuthenticationError,
    GatewayRequest,
    GatewayResponse,
    MalformedResponseError,
    MissingModelError,
    ModelCatalog,
    ModelCatalogEntry,
    ProviderGatewayError,
    ProviderKind,
    ProviderProfile,
    RateLimitError,
    RouteTarget,
    SecretRef,
    TimeoutError,
    UnreachableEndpointError,
    UnsupportedModelError,
    redact_text,
)
from sst.gateway.gateway import ModelGateway, SSTModelGateway
from sst.prompts.dialectic import (
    render_adhd_explorer_prompt,
    render_asd_exploiter_prompt,
    render_cortex_critic_prompt,
    render_cortex_synthesizer_prompt,
    render_critique_prompt,
    render_diverge_prompt,
    render_refine_prompt,
    render_synthesize_prompt,
)
from sst.sandbox.custody import CandidateCustodyManager, PatchApplicationResult
from sst.sandbox.evaluator import SSTDeterministicEvaluator
from sst.search.controller import SSTSearchController
from sst.search.engine import SSTEngine
from sst.search.policy import BudgetTracker, SearchPolicy
from sst.storage.projection import DAGProjection
from sst.storage.serializer import serialize_sst_node, serialize_sst_tree
from sst.storage.store import SQLiteSSTStore
from sst.visualizer.server import (
    VisualizerHandler,
    export_html_visualization,
    render_html_visualizer,
    start_visualizer_server,
    to_cytoscape_elements,
    to_event_delta_payload,
)

__version__ = "0.1.0"

__all__ = [
    # Models
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
    # Contracts
    "TaskPacket",
    "CandidateProposal",
    "ScoreBreakdown",
    "HumanDecisionRecord",
    # Events
    "EventKind",
    "SSTEvent",
    # Errors
    "SSTError",
    "PolicyViolationError",
    "ScopeViolationError",
    "SecurityViolationError",
    "PathTraversalError",
    "BudgetExhaustedError",
    "CustodyError",
    "VerifierError",
    # Storage
    "SQLiteSSTStore",
    "DAGProjection",
    "serialize_sst_node",
    "serialize_sst_tree",
    # Gateway
    "ModelGateway",
    "SSTModelGateway",
    "SSTLLMClient",
    "GatewayRequest",
    "GatewayResponse",
    "ProviderProfile",
    "ProviderKind",
    "RouteTarget",
    "SecretRef",
    "ModelCatalog",
    "ModelCatalogEntry",
    "ProviderGatewayError",
    "UnreachableEndpointError",
    "AuthenticationError",
    "MissingModelError",
    "UnsupportedModelError",
    "RateLimitError",
    "MalformedResponseError",
    "TimeoutError",
    "redact_text",
    # Context
    "ContextCapsuleCompiler",
    "ContextProvider",
    "ArchitectureEvidence",
    # Prompts
    "render_diverge_prompt",
    "render_refine_prompt",
    "render_critique_prompt",
    "render_synthesize_prompt",
    "render_adhd_explorer_prompt",
    "render_asd_exploiter_prompt",
    "render_cortex_critic_prompt",
    "render_cortex_synthesizer_prompt",
    # Sandbox
    "CandidateCustodyManager",
    "PatchApplicationResult",
    "SSTDeterministicEvaluator",
    # Search
    "BudgetTracker",
    "SearchPolicy",
    "SSTEngine",
    "SSTSearchController",
    # Visualizer
    "render_html_visualizer",
    "start_visualizer_server",
    "export_html_visualization",
    "to_cytoscape_elements",
    "to_event_delta_payload",
    "VisualizerHandler",
    # Runner
    "SSTBuildRunner",
]
