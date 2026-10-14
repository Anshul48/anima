"""Semantic Entity-Relationship Graph Engine.

Manages:
1. Node-Attribute Triples across Project, Tool, Goal, Topic, Artifact, Document entities.
2. Directed, typed relations (BELONGS_TO, DEPENDS_ON, EDITING, REFERENCES, CONTRIBUTES_TO, USES).
3. Full provenance links from every node/edge to durable EvidenceRecord IDs.
4. Exporting to normalized DerivedFact collections for downstream consumption.
5. Cryptographic evidence invalidation / tombstone propagation.
"""

from __future__ import annotations

from datetime import datetime, timezone
import re
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from entorhinal.projections.models import (
    EntityNode,
    EntityNodeType,
    RelationEdge,
    RelationType,
    SemanticGraphState,
)
from entorhinal.schemas.models import (
    SOURCE_CLASS_SCOPE_BY_SOURCE_TYPE,
    DerivedFact,
    EvidenceRecord,
    SourceType,
    derive_edge_id,
    derive_fact_id,
    generate_uuidv7,
)


class SemanticGraphManager:
    """Manages the in-memory Entity-Relationship semantic graph and DerivedFact generation."""

    def __init__(self, version: str = "1.0.0") -> None:
        self.version = version
        self._nodes: Dict[str, EntityNode] = {}
        self._edges: List[RelationEdge] = []
        self._node_scopes: Dict[str, List[str]] = {}
        self._last_updated: datetime = datetime.now(timezone.utc)

    def node_scopes(self, entity_uri: str) -> List[str]:
        """Explicit scope tags for a node (record class + entity kind)."""
        return list(self._node_scopes.get(entity_uri, []))

    def _tag_node(self, entity_uri: str, *tags: str) -> None:
        current = set(self._node_scopes.get(entity_uri, []))
        for tag in tags:
            if tag:
                current.add(tag)
        self._node_scopes[entity_uri] = sorted(current)

    # --------------------------------------------------------------------------
    # Node Management
    # --------------------------------------------------------------------------

    def add_or_update_node(
        self,
        entity_uri: str,
        entity_type: Union[EntityNodeType, str],
        name: str,
        attributes: Optional[Dict[str, Any]] = None,
        evidence_ids: Optional[List[str]] = None,
        confidence: float = 1.0,
        observed_at: Optional[datetime] = None,
    ) -> EntityNode:
        """Create or incrementally update an entity node with evidence provenance.

        ``observed_at`` pins node times to evidence time (first-seen minimum
        for created_at, latest maximum for updated_at) so identical evidence
        replays identical node state; callers without evidence time keep the
        wall-clock default.
        """
        now = datetime.now(timezone.utc)
        stamp = observed_at or now
        evidence_list = list(evidence_ids or [])

        if entity_uri in self._nodes:
            existing = self._nodes[entity_uri]
            merged_attrs = dict(existing.attributes)
            if attributes:
                merged_attrs.update(attributes)
            merged_evidence = sorted(set(existing.supporting_evidence_ids + evidence_list))
            try:
                created_at = min(existing.created_at, stamp)
            except TypeError:
                created_at = existing.created_at
            try:
                updated_at = max(existing.updated_at, stamp)
            except TypeError:
                updated_at = stamp
            updated_node = EntityNode(
                entity_uri=entity_uri,
                entity_type=entity_type,
                name=name or existing.name,
                attributes=merged_attrs,
                created_at=created_at,
                updated_at=updated_at,
                supporting_evidence_ids=merged_evidence,
                confidence=min(1.0, max(existing.confidence, confidence)),
            )
            self._nodes[entity_uri] = updated_node
            self._last_updated = now
            return updated_node

        new_node = EntityNode(
            entity_uri=entity_uri,
            entity_type=entity_type,
            name=name,
            attributes=dict(attributes or {}),
            created_at=stamp,
            updated_at=stamp,
            supporting_evidence_ids=sorted(set(evidence_list)),
            confidence=confidence,
        )
        self._nodes[entity_uri] = new_node
        self._last_updated = now
        return new_node

    def get_node(self, entity_uri: str) -> Optional[EntityNode]:
        """Retrieve an entity node by its URI."""
        return self._nodes.get(entity_uri)

    def list_nodes(self, entity_type: Optional[Union[EntityNodeType, str]] = None) -> List[EntityNode]:
        """List nodes matching an optional entity type filter."""
        if entity_type is None:
            return list(self._nodes.values())
        return [n for n in self._nodes.values() if n.entity_type == entity_type]

    # --------------------------------------------------------------------------
    # Edge Management
    # --------------------------------------------------------------------------

    def add_edge(
        self,
        source_uri: str,
        target_uri: str,
        relation_type: Union[RelationType, str],
        confidence: float = 1.0,
        evidence_ids: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        observed_at: Optional[datetime] = None,
    ) -> RelationEdge:
        """Add a directed typed relationship between two entities.

        Edge ids are deterministic over (source, relation, target); validity
        start pins to evidence time when provided.
        """
        now = datetime.now(timezone.utc)
        stamp = observed_at or now
        evidence_list = list(evidence_ids or [])
        rel_name = relation_type.value if isinstance(relation_type, RelationType) else str(relation_type)

        # Check if identical edge already exists
        for edge in self._edges:
            if (
                edge.source_uri == source_uri
                and edge.target_uri == target_uri
                and edge.relation_type == relation_type
            ):
                # Update existing edge
                merged_evidence = sorted(set(edge.supporting_evidence_ids + evidence_list))
                merged_meta = dict(edge.metadata)
                if metadata:
                    merged_meta.update(metadata)

                edge.supporting_evidence_ids = merged_evidence
                edge.confidence = max(edge.confidence, confidence)
                edge.metadata = merged_meta
                try:
                    if stamp < edge.valid_from:
                        edge.valid_from = stamp
                except TypeError:
                    pass
                self._last_updated = now
                return edge

        new_edge = RelationEdge(
            edge_id=derive_edge_id(
                source_uri=source_uri, relation_type=rel_name, target_uri=target_uri
            ),
            source_uri=source_uri,
            target_uri=target_uri,
            relation_type=relation_type,
            confidence=confidence,
            valid_from=stamp,
            valid_to=None,
            supporting_evidence_ids=sorted(set(evidence_list)),
            metadata=dict(metadata or {}),
        )
        self._edges.append(new_edge)
        self._last_updated = now
        return new_edge

    def get_edges(
        self,
        source_uri: Optional[str] = None,
        target_uri: Optional[str] = None,
        relation_type: Optional[Union[RelationType, str]] = None,
    ) -> List[RelationEdge]:
        """Query edges matching source, target, or relation type."""
        results: List[RelationEdge] = []
        for edge in self._edges:
            if source_uri is not None and edge.source_uri != source_uri:
                continue
            if target_uri is not None and edge.target_uri != target_uri:
                continue
            if relation_type is not None and edge.relation_type != relation_type:
                continue
            results.append(edge)
        return results

    # --------------------------------------------------------------------------
    # Deterministic Evidence Ingestion & Entity Extraction
    # --------------------------------------------------------------------------

    def extract_and_ingest_record(self, record: EvidenceRecord) -> None:
        """Deterministically extract entity nodes and relations from an EvidenceRecord."""
        if record.is_tombstone:
            return

        ev_id = record.record_id
        stamp = record.persisted_at
        record_scope = SOURCE_CLASS_SCOPE_BY_SOURCE_TYPE.get(record.source_type.value)

        # 1. Tool Entity (Application)
        tool_uri = f"tool:{self._slugify(record.app_identifier)}"
        self.add_or_update_node(
            entity_uri=tool_uri,
            entity_type=EntityNodeType.TOOL,
            name=record.app_identifier,
            attributes={"source_type": record.source_type.value},
            evidence_ids=[ev_id],
            confidence=1.0,
            observed_at=stamp,
        )
        self._tag_node(tool_uri, record_scope or "")

        # 2. Browser & Web Entities
        if record.source_type == SourceType.BROWSER and record.target_uri:
            uri = record.target_uri

            # GitHub Repository or PR extraction
            gh_match = re.search(r"github\.com/([^/]+/[^/#?]+)(?:/pull/(\d+)|/issues/(\d+))?", uri)
            if gh_match:
                repo_name = gh_match.group(1)
                pr_num = gh_match.group(2)
                issue_num = gh_match.group(3)

                project_uri = f"project:{repo_name}"
                self.add_or_update_node(
                    entity_uri=project_uri,
                    entity_type=EntityNodeType.PROJECT,
                    name=repo_name,
                    attributes={"platform": "github", "repo_url": f"https://github.com/{repo_name}"},
                    evidence_ids=[ev_id],
                    confidence=0.98,
                    observed_at=stamp,
                )
                self._tag_node(project_uri, record_scope or "", "scope:workspace")
                self.add_edge(tool_uri, project_uri, RelationType.USES, confidence=0.95, evidence_ids=[ev_id], observed_at=stamp)

                if pr_num:
                    goal_uri = f"goal:{repo_name}:pr-{pr_num}"
                    title = record.sanitized_payload.get("page_title") or record.window_title or f"PR #{pr_num}"
                    self.add_or_update_node(
                        entity_uri=goal_uri,
                        entity_type=EntityNodeType.GOAL,
                        name=f"Pull Request #{pr_num}: {title}",
                        attributes={"pr_number": int(pr_num), "state": "open"},
                        evidence_ids=[ev_id],
                        confidence=0.95,
                        observed_at=stamp,
                    )
                    self._tag_node(goal_uri, record_scope or "", "scope:workspace")
                    self.add_edge(goal_uri, project_uri, RelationType.BELONGS_TO, confidence=0.99, evidence_ids=[ev_id], observed_at=stamp)
                elif issue_num:
                    goal_uri = f"goal:{repo_name}:issue-{issue_num}"
                    self.add_or_update_node(
                        entity_uri=goal_uri,
                        entity_type=EntityNodeType.GOAL,
                        name=f"Issue #{issue_num}",
                        attributes={"issue_number": int(issue_num)},
                        evidence_ids=[ev_id],
                        confidence=0.95,
                        observed_at=stamp,
                    )
                    self._tag_node(goal_uri, record_scope or "", "scope:workspace")
                    self.add_edge(goal_uri, project_uri, RelationType.BELONGS_TO, confidence=0.99, evidence_ids=[ev_id], observed_at=stamp)

            # ArXiv Papers
            elif "arxiv.org" in uri:
                paper_match = re.search(r"arxiv\.org/(?:abs|pdf)/([0-9.]+)", uri)
                paper_id = paper_match.group(1) if paper_match else uri
                paper_title = record.sanitized_payload.get("paper_title") or record.window_title or f"ArXiv:{paper_id}"
                topic_uri = f"topic:arxiv:{paper_id}"
                self.add_or_update_node(
                    entity_uri=topic_uri,
                    entity_type=EntityNodeType.TOPIC,
                    name=paper_title,
                    attributes={"arxiv_id": paper_id, "url": uri},
                    evidence_ids=[ev_id],
                    confidence=0.95,
                    observed_at=stamp,
                )
                self._tag_node(topic_uri, record_scope or "", "scope:browser")
                self.add_edge(tool_uri, topic_uri, RelationType.REFERENCES, confidence=0.95, evidence_ids=[ev_id], observed_at=stamp)

            # General Documentation / Web Pages
            else:
                doc_uri = f"document:{self._slugify(uri)}"
                title = record.sanitized_payload.get("page_title") or record.window_title or uri
                self.add_or_update_node(
                    entity_uri=doc_uri,
                    entity_type=EntityNodeType.DOCUMENT,
                    name=title,
                    attributes={"url": uri},
                    evidence_ids=[ev_id],
                    confidence=0.90,
                    observed_at=stamp,
                )
                doc_kind = "scope:browser" if uri.lower().startswith(("http://", "https://")) else "scope:workspace"
                self._tag_node(doc_uri, record_scope or "", doc_kind)
                self.add_edge(tool_uri, doc_uri, RelationType.REFERENCES, confidence=0.90, evidence_ids=[ev_id], observed_at=stamp)

        # 3. OS Window & Code Editor Entities
        elif record.source_type in (SourceType.OS_WINDOW, SourceType.DOCUMENT):
            # Check for file path in payload or window title
            file_path = record.sanitized_payload.get("file_path") or record.target_uri
            if not file_path and record.window_title:
                # E.g. "models.py - entorhinal - Visual Studio Code"
                parts = record.window_title.split(" - ")
                if len(parts) >= 2 and "." in parts[0]:
                    file_path = parts[0]

            if file_path:
                artifact_uri = f"artifact:{file_path}"
                self.add_or_update_node(
                    entity_uri=artifact_uri,
                    entity_type=EntityNodeType.ARTIFACT,
                    name=file_path.split("/")[-1].split("\\")[-1],
                    attributes={"file_path": file_path},
                    evidence_ids=[ev_id],
                    confidence=0.95,
                    observed_at=stamp,
                )
                self._tag_node(artifact_uri, record_scope or "", "scope:workspace")
                self.add_edge(tool_uri, artifact_uri, RelationType.EDITING, confidence=0.95, evidence_ids=[ev_id], observed_at=stamp)

                # Check if workspace or repo is present
                ws = record.sanitized_payload.get("workspace") or record.sanitized_payload.get("project")
                if ws:
                    ws_uri = f"workspace:{ws}"
                    self.add_or_update_node(
                        entity_uri=ws_uri,
                        entity_type=EntityNodeType.WORKSPACE,
                        name=ws,
                        attributes={"workspace_name": ws},
                        evidence_ids=[ev_id],
                        confidence=0.95,
                        observed_at=stamp,
                    )
                    self._tag_node(ws_uri, record_scope or "", "scope:workspace")
                    self.add_edge(artifact_uri, ws_uri, RelationType.BELONGS_TO, confidence=0.98, evidence_ids=[ev_id], observed_at=stamp)

        # 4. Terminal PTY Entities
        elif record.source_type == SourceType.TERMINAL_PTY:
            cmd = record.sanitized_payload.get("command") or record.sanitized_payload.get("cmd")
            if cmd:
                # Extract branch changes or pytest runs
                if "git checkout" in cmd or "git switch" in cmd:
                    branch = cmd.split()[-1]
                    branch_uri = f"topic:git-branch:{branch}"
                    self.add_or_update_node(
                        entity_uri=branch_uri,
                        entity_type=EntityNodeType.TOPIC,
                        name=f"Git Branch: {branch}",
                        attributes={"branch": branch, "command": cmd},
                        evidence_ids=[ev_id],
                        confidence=0.95,
                        observed_at=stamp,
                    )
                    self._tag_node(branch_uri, record_scope or "", "scope:terminal")
                elif "pytest" in cmd:
                    pytest_uri = "topic:test-execution:pytest"
                    self.add_or_update_node(
                        entity_uri=pytest_uri,
                        entity_type=EntityNodeType.TOPIC,
                        name="Pytest Test Suite Execution",
                        attributes={"command": cmd, "exit_code": record.sanitized_payload.get("exit_code")},
                        evidence_ids=[ev_id],
                        confidence=0.95,
                        observed_at=stamp,
                    )
                    self._tag_node(pytest_uri, record_scope or "", "scope:terminal")

    # --------------------------------------------------------------------------
    # DerivedFact Export
    # --------------------------------------------------------------------------

    def _export_fact(
        self,
        *,
        entity_uri: str,
        attribute: str,
        value: Any,
        confidence: float,
        valid_from: datetime,
        valid_to: Optional[datetime],
        evidence_ids: List[str],
        derived_by: str,
        scopes: List[str],
    ) -> DerivedFact:
        """Build one derived fact with a stable semantic id (fact-id/1)."""
        ordered_evidence = sorted(set(evidence_ids))
        return DerivedFact(
            fact_id=derive_fact_id(
                entity_uri=entity_uri,
                attribute=attribute,
                value=value,
                valid_from=valid_from,
                valid_to=valid_to,
                evidence_ids=ordered_evidence,
                derived_by=derived_by,
            ),
            schema_version="1.0.0",
            entity_uri=entity_uri,
            attribute=attribute,
            value=value,
            confidence=confidence,
            valid_from=valid_from,
            valid_to=valid_to,
            supporting_evidence_ids=ordered_evidence,
            derived_by=derived_by,
            revision_id=1,
            scopes=sorted(set(scopes)),
        )

    def to_derived_facts(self) -> List[DerivedFact]:
        """Convert all semantic graph nodes and relations into immutable DerivedFact instances.

        Fact ids are deterministic over (entity, attribute, value, validity,
        evidence-set, derivation): identical evidence replays identical ids,
        so correction/explanation/revision anchors survive rebuilds.
        """
        facts: List[DerivedFact] = []

        # 1. Facts from Nodes
        for node in self._nodes.values():
            if not node.supporting_evidence_ids or node.confidence <= 0.0:
                continue
            tags = self.node_scopes(node.entity_uri)

            # Fact for entity presence and classification
            facts.append(
                self._export_fact(
                    entity_uri=node.entity_uri,
                    attribute="entity_type",
                    value=node.entity_type.value if isinstance(node.entity_type, EntityNodeType) else str(node.entity_type),
                    confidence=node.confidence,
                    valid_from=node.created_at,
                    valid_to=None,
                    evidence_ids=node.supporting_evidence_ids,
                    derived_by="SemanticGraphManager.node_type",
                    scopes=tags,
                )
            )

            # Fact for entity name/title
            facts.append(
                self._export_fact(
                    entity_uri=node.entity_uri,
                    attribute="name",
                    value=node.name,
                    confidence=node.confidence,
                    valid_from=node.created_at,
                    valid_to=None,
                    evidence_ids=node.supporting_evidence_ids,
                    derived_by="SemanticGraphManager.node_name",
                    scopes=tags,
                )
            )

            # Facts for individual attributes
            for attr_key, attr_val in node.attributes.items():
                facts.append(
                    self._export_fact(
                        entity_uri=node.entity_uri,
                        attribute=attr_key,
                        value=attr_val,
                        confidence=node.confidence,
                        valid_from=node.updated_at,
                        valid_to=None,
                        evidence_ids=node.supporting_evidence_ids,
                        derived_by=f"SemanticGraphManager.attribute.{attr_key}",
                        scopes=tags,
                    )
                )

        # 2. Facts from Relation Edges
        for edge in self._edges:
            if not edge.supporting_evidence_ids or edge.confidence <= 0.0:
                continue

            rel_name = edge.relation_type.value if isinstance(edge.relation_type, RelationType) else str(edge.relation_type)
            edge_tags = sorted(set(self.node_scopes(edge.source_uri)) | set(self.node_scopes(edge.target_uri)))
            facts.append(
                self._export_fact(
                    entity_uri=edge.source_uri,
                    attribute=f"relation:{rel_name}:{edge.target_uri}",
                    value={
                        "target_uri": edge.target_uri,
                        "relation_type": rel_name,
                        "metadata": edge.metadata,
                    },
                    confidence=edge.confidence,
                    valid_from=edge.valid_from,
                    valid_to=edge.valid_to,
                    evidence_ids=edge.supporting_evidence_ids,
                    derived_by="SemanticGraphManager.relation_edge",
                    scopes=edge_tags,
                )
            )

        return facts

    # --------------------------------------------------------------------------
    # Tombstone & Provenance Invalidation
    # --------------------------------------------------------------------------

    def invalidate_evidence(self, evidence_id: str) -> List[str]:
        """Purge an evidence record reference across all nodes and edges.

        Returns list of affected entity URIs.
        """
        affected_uris: Set[str] = set()

        # Update nodes
        for uri, node in list(self._nodes.items()):
            if evidence_id in node.supporting_evidence_ids:
                affected_uris.add(uri)
                remaining_evidence = [e for e in node.supporting_evidence_ids if e != evidence_id]
                if not remaining_evidence:
                    # Remove node entirely if zero supporting evidence remains
                    del self._nodes[uri]
                    self._node_scopes.pop(uri, None)
                else:
                    node.supporting_evidence_ids = sorted(set(remaining_evidence))

        # Update edges
        updated_edges: List[RelationEdge] = []
        for edge in self._edges:
            if evidence_id in edge.supporting_evidence_ids:
                affected_uris.add(edge.source_uri)
                affected_uris.add(edge.target_uri)
                remaining_edge_ev = [e for e in edge.supporting_evidence_ids if e != evidence_id]
                if remaining_edge_ev:
                    edge.supporting_evidence_ids = sorted(set(remaining_edge_ev))
                    updated_edges.append(edge)
            else:
                updated_edges.append(edge)
        self._edges = updated_edges

        self._last_updated = datetime.now(timezone.utc)
        return sorted(affected_uris)

    # --------------------------------------------------------------------------
    # Export / Import & Snapshotting
    # --------------------------------------------------------------------------

    def export_state(self) -> SemanticGraphState:
        """Export the current graph as a sealed SemanticGraphState."""
        return SemanticGraphState(
            graph_id=generate_uuidv7(),
            version=self.version,
            nodes=dict(self._nodes),
            edges=list(self._edges),
            last_updated=self._last_updated,
        )

    def import_state(self, state: SemanticGraphState) -> None:
        """Load graph state from a SemanticGraphState object."""
        self.version = state.version
        self._nodes = dict(state.nodes)
        self._edges = list(state.edges)
        # Imported nodes carry no stored tags; the fixed URI fallback table
        # still applies at match time (default-deny for unknown schemes).
        self._node_scopes = {}
        self._last_updated = state.last_updated

    def clear(self) -> None:
        """Reset the graph state completely."""
        self._nodes.clear()
        self._edges.clear()
        self._node_scopes.clear()
        self._last_updated = datetime.now(timezone.utc)

    # --------------------------------------------------------------------------
    # Helper
    # --------------------------------------------------------------------------

    def _slugify(self, text: str) -> str:
        """Convert arbitrary string into normalized URI slug."""
        clean = re.sub(r"[^\w\-_/.]", "_", text.strip().lower())
        return clean.strip("_")
