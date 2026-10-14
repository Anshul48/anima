# SST Data Contracts & Event Schema

> **Document Version:** 1.0.0  
> **Package:** `sst-engine` (`src/sst/core`, `src/sst/storage`)  
> **Status:** Production Architecture Standard  

---

## 1. Pydantic V2 Immutable Execution Contracts

All primary communication between the search controller, sandboxes, model gateways, and human operators uses strict, immutable Pydantic V2 data contracts (`frozen=True`).

### 1.1 `TaskPacket`
The root specification defining the boundary and acceptance criteria of a search task:

```python
class TaskPacket(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    task_id: str
    goal: str
    source_repo_root: str
    base_commit: str
    snapshot_hash: str
    allowed_paths: list[str] = Field(default_factory=list)
    forbidden_paths: list[str] = Field(default_factory=list)
    invariants: list[str] = Field(default_factory=list)
    acceptance_commands: list[str] = Field(default_factory=list)
    timeout_seconds: int = 120
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def compute_hash(self) -> str:
        """Computes a deterministic SHA-256 fingerprint of task parameters."""
        data = f"{self.task_id}:{self.goal}:{self.base_commit}:{self.snapshot_hash}:{sorted(self.allowed_paths)}:{sorted(self.forbidden_paths)}"
        return hashlib.sha256(data.encode("utf-8")).hexdigest()
```

### 1.2 `CandidateProposal`
Represents a discrete candidate patch produced during the expansion or refinement steps:

```python
class CandidateProposal(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    candidate_id: str
    tree_id: str
    parent_id: str | None = None
    role: NodeRole = NodeRole.DIVERGE
    title: str
    rationale: str
    target_paths: list[str] = Field(default_factory=list)
    patch_diff: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def compute_digest(self) -> str:
        """Returns deterministic SHA-256 hash of the proposed patch and target paths."""
        data = f"{self.candidate_id}:{sorted(self.target_paths)}:{self.patch_diff}"
        return hashlib.sha256(data.encode("utf-8")).hexdigest()
```

### 1.3 `ScoreBreakdown`
Deterministic breakdown of qualitative and quantitative metrics assigned by semantic critics:

```python
class ScoreBreakdown(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    candidate_id: str
    value_score: float = Field(ge=0.0, le=1.0)
    verdict: str  # "APPROVE", "REJECT", "ESCALATE_HUMAN"
    correctness_score: float = Field(default=1.0, ge=0.0, le=1.0)
    architectural_fit: float = Field(default=1.0, ge=0.0, le=1.0)
    complexity_penalty: float = Field(default=0.0, ge=0.0, le=1.0)
    critique: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
```

### 1.4 `HumanDecisionRecord`
Cryptographic and auditable record of manual operator interventions:

```python
class HumanDecisionRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    decision_id: str
    tree_id: str
    candidate_id: str
    operator: str
    verdict: str  # "APPROVED", "REJECTED"
    reason: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
```

---

## 2. Core Search Models (`src/sst/core/models.py`)

### 2.1 `SSTNode`
Represents an individual node in the State Space Tree:

```python
class SSTNode(BaseModel):
    model_config = ConfigDict(extra="ignore")

    node_id: str
    parent_id: str | None = None
    tree_id: str
    depth: int = 0
    domain: DomainMode = DomainMode.AUTOBUILD
    role: NodeRole
    title: str
    payload_type: PayloadType = PayloadType.CODE_DIFF
    content: str
    status: NodeStatus = NodeStatus.PROPOSED
    visit_count: int = 0
    value_score: float = 0.0
    deterministic_result: DeterministicGateResult | None = None
    cortex_evaluation: CortexEvaluation | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
```

### 2.2 `SSTTree`
In-memory Directed Acyclic Graph projection of the search space:

```python
class SSTTree(BaseModel):
    model_config = ConfigDict(extra="ignore")

    tree_id: str
    domain: DomainMode = DomainMode.AUTOBUILD
    root_goal: str
    root_node_id: str
    nodes: dict[str, SSTNode] = Field(default_factory=dict)
    winning_path: list[str] = Field(default_factory=list)
```

---

## 3. Enumerations & Standard Vocabularies

```python
class DomainMode(StrEnum):
    AUTOBUILD = "AUTOBUILD"
    AUTORESEARCH = "AUTORESEARCH"


class NodeRole(StrEnum):
    CORTEX_PLANNER = "CORTEX_PLANNER"
    DIVERGE = "DIVERGE"
    REFINE = "REFINE"
    CRITIQUE = "CRITIQUE"
    SYNTHESIZE = "SYNTHESIZE"
    HUMAN_DECISION = "HUMAN_DECISION"


class NodeStatus(StrEnum):
    PROPOSED = "PROPOSED"
    PASS_DETERMINISTIC = "PASS_DETERMINISTIC"
    FAIL_DETERMINISTIC = "FAIL_DETERMINISTIC"
    APPROVED_CORTEX = "APPROVED_CORTEX"
    PRUNED_SEMANTIC = "PRUNED_SEMANTIC"
    SYNTHESIZED = "SYNTHESIZED"
    ESCALATE_HUMAN = "ESCALATE_HUMAN"
    REJECTED_HUMAN = "REJECTED_HUMAN"
    PROMOTED = "PROMOTED"


class PayloadType(StrEnum):
    GOAL = "GOAL"
    PLAN = "PLAN"
    CODE_DIFF = "CODE_DIFF"
    SYNTHESIS = "SYNTHESIS"
    CRITIQUE = "CRITIQUE"


class EventKind(StrEnum):
    TREE_CREATED = "TREE_CREATED"
    NODE_PROPOSED = "NODE_PROPOSED"
    VERIFIER_FINISHED = "VERIFIER_FINISHED"
    SCORE_RECORDED = "SCORE_RECORDED"
    NODE_PRUNED = "NODE_PRUNED"
    NODE_SYNTHESIZED = "NODE_SYNTHESIZED"
    HUMAN_DECISION_REQUESTED = "HUMAN_DECISION_REQUESTED"
    HUMAN_DECISION_RECORDED = "HUMAN_DECISION_RECORDED"
    PROMOTION_RECOMMENDED = "PROMOTION_RECOMMENDED"
    PROMOTED_TO_WORKSPACE = "PROMOTED_TO_WORKSPACE"
    CANCELLATION_REQUESTED = "CANCELLATION_REQUESTED"
```

---

## 4. SQLite WAL Storage Schema

All tree state is persisted in SQLite using Write-Ahead Logging (`PRAGMA journal_mode=WAL;`):

```sql
CREATE TABLE IF NOT EXISTS sst_events (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE,
    tree_id TEXT NOT NULL,
    node_id TEXT,
    kind TEXT NOT NULL,
    actor TEXT NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE,
    payload TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_sst_events_tree_id ON sst_events(tree_id);
CREATE INDEX IF NOT EXISTS idx_sst_events_node_id ON sst_events(node_id);

CREATE TABLE IF NOT EXISTS sst_leases (
    lease_key TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL,
    expires_at REAL NOT NULL
);
```

### Concurrency & Idempotency Rules
1. **Idempotent Insertion**: Attempting to insert an event with an existing `idempotency_key` is silently ignored (`INSERT OR IGNORE`), ensuring network retries cannot corrupt tree history.
2. **Deterministic Replay**: The complete DAG state (`SSTTree`) can be reproduced by calling `store.rebuild_tree_from_events(tree_id)`, replaying mutations in strict sequence order `seq ASC`.
3. **Lease Locking**: Distributed workers acquire time-bounded optimistic locks in `sst_leases` to prevent concurrent mutations on identical frontier nodes.
