"""Entorhinal: Local-first, user-controlled contextual intelligence system.

Core Invariants:
1. Standalone operational autonomy (100% functional without Reflex or Trace).
2. Zero action authority (purely observational and advisory context).
3. Epistemic separation (Evidence != Facts != Hypotheses != ContextSnapshots != User Corrections).
4. Deterministic baseline first.
5. Privacy by design with pre-storage policy gating.
6. Cryptographic provenance with SHA-256 hash chains.
7. Rebuildable semantic projections.
"""

from entorhinal.api import app, create_app
from entorhinal.evals import (
    ChaosHarness,
    EvalRunner,
    EvaluationReport,
    IndependenceAuditor,
    IndependenceReport,
    PrivacyStressTester,
)
from entorhinal.evidence import (
    DeterministicReplayEngine,
    EvidenceJournal,
    ProjectionStager,
    SecondaryIndexManager,
    StagedProjectionContext,
)
from entorhinal.ingest import HIGH_PRIORITY_SOURCES, IngestionPipeline
from entorhinal.policy.engine import PolicyEngine
from entorhinal.ports.interfaces import MemoryPort, QueryPort, SourcePort, UserControlPort
from entorhinal.projections import (
    EntityNode,
    EntityNodeType,
    HypothesisManager,
    ImmediateFocusState,
    MultiTimescaleCompiler,
    MultiTimescaleContext,
    ProjectionCompiler,
    RelationEdge,
    RelationType,
    SemanticGraphManager,
    SemanticGraphState,
    SessionClusterEngine,
    SessionTaskCluster,
    UncertaintyEngine,
)
from entorhinal.query import ContextSnapshotService, ExplanationEngine, PermissionDeniedError
from entorhinal.schemas.models import (
    ClassificationLevel,
    ContextRequest,
    ContextSnapshot,
    CorrectionAction,
    DerivedFact,
    EvidenceRecord,
    FactExplanation,
    Hypothesis,
    PolicyDecision,
    RawSignalEvent,
    SourceType,
    TombstoneRecord,
    UserCorrection,
)
from entorhinal.sources import (
    BaseSourceAdapter,
    BrowserSourceAdapter,
    MockSourceAdapter,
    OSWindowSourceAdapter,
    TerminalPTYSourceAdapter,
)
from entorhinal.tool_qualification.framework import (
    DecisionClass,
    FallbackRegistry,
    ToolQualificationDossier,
    ToolQualificationHarness,
)
from entorhinal.user_control import (
    AuditLogManager,
    CascadeDeletionEngine,
    CorrectionManager,
    UserControlService,
)

__version__ = "0.4.0"

__all__ = [
    "AuditLogManager",
    "BaseSourceAdapter",
    "BrowserSourceAdapter",
    "CascadeDeletionEngine",
    "ChaosHarness",
    "ClassificationLevel",
    "ContextRequest",
    "ContextSnapshot",
    "ContextSnapshotService",
    "CorrectionAction",
    "CorrectionManager",
    "DecisionClass",
    "DerivedFact",
    "DeterministicReplayEngine",
    "EntityNode",
    "EntityNodeType",
    "EvalRunner",
    "EvaluationReport",
    "EvidenceJournal",
    "EvidenceRecord",
    "ExplanationEngine",
    "FactExplanation",
    "FallbackRegistry",
    "HIGH_PRIORITY_SOURCES",
    "Hypothesis",
    "HypothesisManager",
    "ImmediateFocusState",
    "IndependenceAuditor",
    "IndependenceReport",
    "IngestionPipeline",
    "MemoryPort",
    "MockSourceAdapter",
    "MultiTimescaleCompiler",
    "MultiTimescaleContext",
    "OSWindowSourceAdapter",
    "PermissionDeniedError",
    "PolicyDecision",
    "PolicyEngine",
    "PrivacyStressTester",
    "ProjectionCompiler",
    "ProjectionStager",
    "QueryPort",
    "RawSignalEvent",
    "RelationEdge",
    "RelationType",
    "SecondaryIndexManager",
    "SemanticGraphManager",
    "SemanticGraphState",
    "SessionClusterEngine",
    "SessionTaskCluster",
    "SourcePort",
    "SourceType",
    "StagedProjectionContext",
    "TerminalPTYSourceAdapter",
    "TombstoneRecord",
    "ToolQualificationDossier",
    "ToolQualificationHarness",
    "UncertaintyEngine",
    "UserControlPort",
    "UserControlService",
    "UserCorrection",
    "__version__",
    "app",
    "create_app",
]
