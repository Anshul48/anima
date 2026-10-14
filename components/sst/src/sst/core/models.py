"""Core data models for State Space Tree (SST) and asymmetric dialectic MCTS search."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class DomainMode(StrEnum):
    AUTOBUILD = "AUTOBUILD"
    AUTORESEARCH = "AUTORESEARCH"


class NodeRole(StrEnum):
    # Modern functional roles
    PLANNER = "PLANNER"
    DIVERGE = "DIVERGE"
    REFINE = "REFINE"
    CRITIQUE = "CRITIQUE"
    SYNTHESIZE = "SYNTHESIZE"
    HUMAN_DECISION = "HUMAN_DECISION"

    # Backward compatibility aliases
    CORTEX_PLANNER = "CORTEX_PLANNER"
    ADHD_EXPLORER = "ADHD_EXPLORER"
    ASD_EXPLOITER = "ASD_EXPLOITER"
    CORTEX_CRITIC = "CORTEX_CRITIC"
    HUMAN_ORACLE = "HUMAN_ORACLE"


class NodeStatus(StrEnum):
    UNEXPANDED = "UNEXPANDED"
    EVALUATING = "EVALUATING"
    PASS_DETERMINISTIC = "PASS_DETERMINISTIC"
    FAIL_DETERMINISTIC = "FAIL_DETERMINISTIC"
    PRUNED_SEMANTIC = "PRUNED_SEMANTIC"
    APPROVED_CORTEX = "APPROVED_CORTEX"
    SYNTHESIZED = "SYNTHESIZED"
    AWAITING_HUMAN_ORACLE = "AWAITING_HUMAN_ORACLE"
    REJECTED_HUMAN = "REJECTED_HUMAN"


class PayloadType(StrEnum):
    GOAL = "GOAL"
    CODE_DIFF = "CODE_DIFF"
    HYPOTHESIS = "HYPOTHESIS"
    EXPERIMENT_TRIAL = "EXPERIMENT_TRIAL"
    SYNTHESIS = "SYNTHESIS"


class AuDHDContextCapsule(BaseModel):
    """Immutable, bounded context capsule supplied to exploration/exploitation nodes."""

    goal: str
    invariants: list[str] = Field(default_factory=list)
    interfaces: list[str] = Field(default_factory=list)
    relevant_files: dict[str, str] = Field(default_factory=dict)
    literature_or_prior_insights: list[str] = Field(default_factory=list)
    action_space_boundary: str = ""
    negative_constraints: list[str] = Field(default_factory=list)
    # Memory provenance (additive; populated from the compiler's last_report).
    memory_provider: str = "none"
    memory_availability: str = "UNAVAILABLE"
    memory_evidence_refs: list[str] = Field(default_factory=list)


ContextCapsule = AuDHDContextCapsule


class AcceptanceCommandResult(BaseModel):
    """Per-command outcome of a multi-command acceptance gate run."""

    model_config = ConfigDict(frozen=True)

    command: str
    exit_code: int
    passed: bool
    stdout: str = ""
    stderr: str = ""
    duration_seconds: float = 0.0


class DeterministicGateResult(BaseModel):
    """Result of sandbox evaluation (linters, test suites, sanity checks)."""

    passed: bool
    exit_code: int = 0
    stdout: str = ""
    stderr: str = ""
    duration_seconds: float = 0.0
    metrics: dict[str, float] = Field(default_factory=dict)
    failure_reason: str | None = None
    regression_detected: bool = False
    tests_passed: int = 0
    tests_failed: int = 0
    command_results: list[AcceptanceCommandResult] = Field(default_factory=list)
    patch_hash: str = ""
    post_patch_digest: str = ""


class CortexEvaluation(BaseModel):
    """Semantic critique, value scoring, and synthesis guidance from the frontier model."""

    verdict: str  # "APPROVE", "PRUNE", "SYNTHESIZE", "ESCALATE_HUMAN"
    value_score: float = Field(default=0.0, ge=0.0, le=1.0)
    architectural_fit: float = Field(default=0.0, ge=0.0, le=1.0)
    critique: str = ""
    synthesis_hints: list[str] = Field(default_factory=list)
    human_escalation_reason: str | None = None


class SSTNode(BaseModel):
    """Atomic state node in the State Space Tree."""

    node_id: str
    parent_id: str | None = None
    tree_id: str
    depth: int = 0
    domain: DomainMode
    role: NodeRole
    title: str
    status: NodeStatus = NodeStatus.UNEXPANDED

    # Model and generation hyperparameters
    model: str = ""
    temperature: float = 0.7
    context_tokens: int = 0

    # Content payload
    payload_type: PayloadType
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)

    # MCTS & Evaluation state
    visit_count: int = 0
    uct_score: float = 0.0
    deterministic_result: DeterministicGateResult | None = None
    cortex_evaluation: CortexEvaluation | None = None
    prune_reason: str | None = None

    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @property
    def value_score(self) -> float:
        if self.cortex_evaluation:
            return self.cortex_evaluation.value_score
        if self.deterministic_result and self.deterministic_result.passed:
            return 0.5
        return 0.0


class SSTTree(BaseModel):
    """The State Space Tree holding nodes, edges, frontier, and winning paths."""

    tree_id: str
    domain: DomainMode
    root_goal: str
    root_node_id: str
    nodes: dict[str, SSTNode] = Field(default_factory=dict)
    active_frontier: list[str] = Field(default_factory=list)
    pruned_nodes: list[str] = Field(default_factory=list)
    winning_path: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def add_node(self, node: SSTNode) -> None:
        self.nodes[node.node_id] = node
        if node.status in {
            NodeStatus.UNEXPANDED,
            NodeStatus.PASS_DETERMINISTIC,
            NodeStatus.APPROVED_CORTEX,
            NodeStatus.SYNTHESIZED,
        }:
            if node.node_id not in self.active_frontier:
                self.active_frontier.append(node.node_id)
        elif node.status in {NodeStatus.FAIL_DETERMINISTIC, NodeStatus.PRUNED_SEMANTIC, NodeStatus.REJECTED_HUMAN}:
            if node.node_id in self.active_frontier:
                self.active_frontier.remove(node.node_id)
            if node.node_id not in self.pruned_nodes:
                self.pruned_nodes.append(node.node_id)

    def get_children(self, parent_id: str) -> list[SSTNode]:
        return [n for n in self.nodes.values() if n.parent_id == parent_id]
