"""Multi-Timescale Semantic Projection Models and Schema Definitions.

Defines schemas for:
- Immediate Focus State (seconds)
- Session Task Clusters (hours)
- Entity-Relationship Semantic Graph Nodes and Edges (days/weeks)
- Semantic Graph State
- Unified Multi-Timescale Context View
- ProjectionCompiler abstract interface

Invariants:
1. Purely observational / advisory structures (zero action authority).
2. Epistemic separation: Evidence != Derived Facts != Hypotheses != ContextSnapshots.
3. Every graph node and relation edge maintains explicit supporting_evidence_ids.
4. Hypotheses carry is_hypothesis=True.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, ConfigDict, Field

from entorhinal.schemas.models import (
    DerivedFact,
    EvidenceRecord,
    Hypothesis,
    SourceType,
    generate_uuidv7,
)


# ==============================================================================
# Graph Node & Relation Enumerations
# ==============================================================================

class EntityNodeType(str, Enum):
    """Categorical types of entities tracked in the semantic graph."""
    PROJECT = "Project"
    TOOL = "Tool"
    GOAL = "Goal"
    TOPIC = "Topic"
    ARTIFACT = "Artifact"
    REPOSITORY = "Repository"
    DOCUMENT = "Document"
    WORKSPACE = "Workspace"
    UNKNOWN = "Unknown"


class RelationType(str, Enum):
    """Typed relationship edges between semantic graph entities."""
    BELONGS_TO = "BELONGS_TO"
    DEPENDS_ON = "DEPENDS_ON"
    EDITING = "EDITING"
    REFERENCES = "REFERENCES"
    CONTRIBUTES_TO = "CONTRIBUTES_TO"
    USES = "USES"
    RELATED_TO = "RELATED_TO"
    PART_OF = "PART_OF"
    PRODUCES = "PRODUCES"


# ==============================================================================
# Horizon 1: Immediate Focus State (1s - 5m)
# ==============================================================================

class ImmediateFocusState(BaseModel):
    """Real-time representation of the user's current foreground focus."""
    model_config = ConfigDict(extra="forbid")

    focus_id: str = Field(default_factory=generate_uuidv7, description="UUIDv7 focus snapshot ID")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC observation timestamp"
    )
    app_identifier: str = Field(..., min_length=1, description="Active application name/process")
    window_title: Optional[str] = Field(default=None, description="Active window title")
    target_uri: Optional[str] = Field(default=None, description="Active document path or web URL")
    focused_element: Optional[str] = Field(default=None, description="Focused DOM/UI element or cursor symbol")
    selected_text: Optional[str] = Field(default=None, description="Currently highlighted text selection")
    source_type: SourceType = Field(default=SourceType.OS_WINDOW, description="Source category")
    duration_seconds: float = Field(default=0.0, ge=0.0, description="Dwell duration in this focus state")
    supporting_evidence_id: Optional[str] = Field(default=None, description="Originating EvidenceRecord ID")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional context metadata")


# ==============================================================================
# Horizon 2: Session Task Cluster (5m - 8h)
# ==============================================================================

class SessionTaskCluster(BaseModel):
    """Cohesive cluster of interleaved application events forming a distinct task workflow."""
    model_config = ConfigDict(extra="forbid")

    cluster_id: str = Field(default_factory=generate_uuidv7, description="UUIDv7 session cluster ID")
    title: str = Field(default="Active Task Session", description="Descriptive task title")
    start_time: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC cluster start timestamp"
    )
    end_time: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC cluster end timestamp"
    )
    primary_app: str = Field(default="", description="Dominant application in this cluster")
    primary_topic: str = Field(default="", description="Dominant topic or repository")
    associated_apps: List[str] = Field(default_factory=list, description="Unique applications used in session")
    associated_uris: List[str] = Field(default_factory=list, description="Unique URIs/files accessed")
    event_count: int = Field(default=0, ge=0, description="Total evidence records clustered")
    duration_seconds: float = Field(default=0.0, ge=0.0, description="Total duration of task session")
    supporting_evidence_ids: List[str] = Field(
        default_factory=list,
        description="All EvidenceRecord UUIDs comprising this cluster"
    )
    centroid_terms: Dict[str, float] = Field(
        default_factory=dict,
        description="Term frequency centroid vector for semantic similarity"
    )
    is_transient: bool = Field(
        default=False,
        description="True if this cluster is a brief transient switch (<30s)"
    )
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional session metadata")


# ==============================================================================
# Horizon 3: Project & Entity Graph (1d - 30d)
# ==============================================================================

class EntityNode(BaseModel):
    """Node in the local semantic entity graph."""
    model_config = ConfigDict(extra="forbid")

    entity_uri: str = Field(..., min_length=1, description="Unique URI identifying the entity")
    entity_type: Union[EntityNodeType, str] = Field(
        default=EntityNodeType.UNKNOWN,
        description="Entity category"
    )
    name: str = Field(..., min_length=1, description="Human-readable entity name")
    attributes: Dict[str, Any] = Field(default_factory=dict, description="Semantic attribute key-value pairs")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC creation timestamp"
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC last updated timestamp"
    )
    supporting_evidence_ids: List[str] = Field(
        default_factory=list,
        description="Evidence records grounding this node"
    )
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Confidence score [0.0, 1.0]")


class RelationEdge(BaseModel):
    """Directed, typed relationship edge connecting two entities with provenance."""
    model_config = ConfigDict(extra="forbid")

    edge_id: str = Field(default_factory=generate_uuidv7, description="UUIDv7 edge ID")
    source_uri: str = Field(..., min_length=1, description="Source entity URI")
    target_uri: str = Field(..., min_length=1, description="Target entity URI")
    relation_type: Union[RelationType, str] = Field(..., description="Relationship type")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Edge confidence score [0.0, 1.0]")
    valid_from: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC validity start timestamp"
    )
    valid_to: Optional[datetime] = Field(default=None, description="UTC validity end timestamp")
    supporting_evidence_ids: List[str] = Field(
        default_factory=list,
        description="Evidence records grounding this relation"
    )
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional relation metadata")


class SemanticGraphState(BaseModel):
    """Snapshot representation of the full in-memory semantic graph."""
    model_config = ConfigDict(extra="forbid")

    graph_id: str = Field(default_factory=generate_uuidv7, description="UUIDv7 graph state ID")
    version: str = Field(default="1.0.0", description="Schema version")
    nodes: Dict[str, EntityNode] = Field(default_factory=dict, description="Nodes indexed by entity_uri")
    edges: List[RelationEdge] = Field(default_factory=list, description="All directed relation edges")
    last_updated: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp of last graph update"
    )


# ==============================================================================
# Unified Multi-Timescale Context View
# ==============================================================================

class MultiTimescaleContext(BaseModel):
    """Unified composite view across all four operational timescales."""
    model_config = ConfigDict(extra="forbid")

    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC snapshot timestamp"
    )
    immediate_focus: Union[ImmediateFocusState, Dict[str, Any]] = Field(
        default_factory=dict,
        description="Current active focus (1s - 5m)"
    )
    active_session_cluster: Union[SessionTaskCluster, Dict[str, Any]] = Field(
        default_factory=dict,
        description="Current task session cluster (5m - 8h)"
    )
    active_project_nodes: List[str] = Field(
        default_factory=list,
        description="Active project URIs and open goals (1d - 30d)"
    )
    long_horizon_traits: Dict[str, Any] = Field(
        default_factory=dict,
        description="Persistent developer traits, preferences, and habits (1m - 1y)"
    )
    active_facts_count: int = Field(default=0, ge=0, description="Total active derived facts")
    active_hypotheses_count: int = Field(default=0, ge=0, description="Total active hypotheses")


# ==============================================================================
# Abstract Projection Compiler Interface
# ==============================================================================

class ProjectionCompiler(ABC):
    """Abstract interface for multi-timescale semantic projection compilers."""

    @abstractmethod
    def process_incremental_event(self, record: EvidenceRecord) -> None:
        """Updates fast in-memory immediate focus and active session state (<5ms)."""
        pass

    @abstractmethod
    async def compile_batch_projection(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> List[DerivedFact]:
        """Runs deterministic entity extraction and semantic graph updates over time window."""
        pass

    @abstractmethod
    async def propose_hypotheses(
        self,
        cluster_data: Union[Dict[str, Any], SessionTaskCluster],
    ) -> List[Hypothesis]:
        """Generates candidate intent labels with calibrated uncertainty and evidence links."""
        pass

    @abstractmethod
    def get_current_context(self) -> MultiTimescaleContext:
        """Returns the real-time composite multi-timescale state."""
        pass
