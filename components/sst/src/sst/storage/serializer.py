"""JSON DAG graph serializers for SST visualization in UI and web tools."""

from __future__ import annotations

from typing import Any

from sst.core.models import NodeRole, NodeStatus, SSTNode, SSTTree


def serialize_sst_node(node: SSTNode) -> dict[str, Any]:
    """Converts an SST node to a UI-friendly dictionary representation."""
    diff_snippet = node.content[:300] + ("..." if len(node.content) > 300 else "")
    return {
        "id": node.node_id,
        "parentId": node.parent_id,
        "title": node.title,
        "depth": node.depth,
        "role": node.role.value,
        "status": node.status.value,
        "model": node.model,
        "temperature": node.temperature,
        "payloadType": node.payload_type.value,
        "diffPreview": diff_snippet,
        "visitCount": node.visit_count,
        "uctScore": round(float(node.uct_score), 4),
        "valueScore": round(float(node.value_score), 4),
        "deterministicPass": node.deterministic_result.passed if node.deterministic_result else None,
        "deterministicDuration": round(float(node.deterministic_result.duration_seconds), 3)
        if node.deterministic_result
        else None,
        "pruneReason": node.prune_reason,
        "cortexVerdict": node.cortex_evaluation.verdict if node.cortex_evaluation else None,
        "cortexCritique": node.cortex_evaluation.critique if node.cortex_evaluation else None,
        "createdAt": node.created_at.isoformat(),
        "updatedAt": node.updated_at.isoformat(),
        "epoch": node.metadata.get("epoch", node.depth),
        "validTo": node.metadata.get("valid_to"),
        "notes": node.metadata.get("notes", node.content),
        "branchedFrom": node.metadata.get("branched_from", node.parent_id),
        "supersededBy": node.metadata.get("superseded_by"),
        "metadata": node.metadata,
    }


def serialize_sst_tree(tree: SSTTree) -> dict[str, Any]:
    """Converts the full SST tree into a DAG graph schema for visualizers (Cytoscape / React Flow)."""
    serialized_nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []

    for node in tree.nodes.values():
        serialized_nodes.append(serialize_sst_node(node))
        parent_ids: list[str] = list(node.metadata.get("parent_ids", []))
        if node.parent_id and node.parent_id not in parent_ids:
            parent_ids.append(node.parent_id)

        for pid in parent_ids:
            if pid in tree.nodes:
                edge_type = "EXPLORATION"
                if node.role in (NodeRole.REFINE, NodeRole.ASD_EXPLOITER):
                    edge_type = "EXPLOITATION_REFACTOR"
                elif (
                    node.role in (NodeRole.CRITIQUE, NodeRole.SYNTHESIZE, NodeRole.CORTEX_CRITIC)
                    or node.status == NodeStatus.SYNTHESIZED
                    or len(parent_ids) > 1
                ):
                    edge_type = "SYNTHESIS"
                elif node.role in (NodeRole.HUMAN_DECISION, NodeRole.HUMAN_ORACLE):
                    edge_type = "HUMAN_DECISION"

                edges.append(
                    {
                        "id": f"edge_{pid}_{node.node_id}",
                        "source": pid,
                        "target": node.node_id,
                        "type": edge_type,
                        "status": node.status.value,
                        "createdAt": node.created_at.isoformat(),
                        "epoch": node.metadata.get("epoch", node.depth),
                        "relation": node.metadata.get("edge_relations", {}).get(pid, edge_type),
                    }
                )

    return {
        "treeId": tree.tree_id,
        "domain": tree.domain.value,
        "rootGoal": tree.root_goal,
        "rootNodeId": tree.root_node_id,
        "totalNodeCount": len(tree.nodes),
        "activeFrontierCount": len(tree.active_frontier),
        "prunedNodeCount": len(tree.pruned_nodes),
        "winningPath": tree.winning_path,
        "nodes": serialized_nodes,
        "edges": edges,
    }
