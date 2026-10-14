"""Deterministic DAG and state tree projection reconstructed from immutable events."""

from __future__ import annotations

from sst.core.events import EventKind, SSTEvent
from sst.core.models import (
    CortexEvaluation,
    DeterministicGateResult,
    DomainMode,
    NodeRole,
    NodeStatus,
    PayloadType,
    SSTNode,
    SSTTree,
)


class DAGProjection:
    """Rebuilds a complete, consistent SSTTree DAG from an immutable sequence of events."""

    @staticmethod
    def replay_events(events: list[SSTEvent], initial_tree_id: str | None = None) -> SSTTree:
        """Deterministically replays events to build the current DAG projection."""
        tree: SSTTree | None = None

        for event in events:
            kind = event.kind
            payload = event.payload
            node_id = event.node_id

            if kind == EventKind.TREE_CREATED:
                tree_id = str(payload.get("tree_id", event.tree_id))
                domain_str = str(payload.get("domain", "AUTOBUILD"))
                domain = DomainMode(domain_str) if domain_str in DomainMode.__members__ else DomainMode.AUTOBUILD
                root_goal = str(payload.get("root_goal", ""))
                root_node_id = str(payload.get("root_node_id", f"root_{tree_id}"))

                root_node = SSTNode(
                    node_id=root_node_id,
                    parent_id=None,
                    tree_id=tree_id,
                    depth=0,
                    domain=domain,
                    role=NodeRole.PLANNER,
                    title=f"Goal: {root_goal[:60]}",
                    payload_type=PayloadType.GOAL,
                    content=root_goal,
                    status=NodeStatus.APPROVED_CORTEX,
                )

                tree = SSTTree(
                    tree_id=tree_id,
                    domain=domain,
                    root_goal=root_goal,
                    root_node_id=root_node_id,
                    nodes={root_node_id: root_node},
                    active_frontier=[root_node_id],
                    winning_path=[root_node_id],
                )

            elif tree is not None:
                if kind in {EventKind.NODE_PROPOSED, EventKind.CANDIDATE_CREATED}:
                    if not node_id:
                        continue
                    parent_id = str(payload.get("parent_id", tree.root_node_id))
                    parent_node = tree.nodes.get(parent_id)
                    depth = (parent_node.depth + 1) if parent_node else 1

                    role_str = str(payload.get("role", "DIVERGE"))
                    role_map = {
                        "DIVERGE": NodeRole.DIVERGE,
                        "REFINE": NodeRole.REFINE,
                        "CRITIQUE": NodeRole.CRITIQUE,
                        "SYNTHESIZE": NodeRole.SYNTHESIZE,
                        "HUMAN_DECISION": NodeRole.HUMAN_DECISION,
                        "PLANNER": NodeRole.PLANNER,
                        "ADHD_EXPLORER": NodeRole.DIVERGE,
                        "ASD_EXPLOITER": NodeRole.REFINE,
                        "CORTEX_CRITIC": NodeRole.CRITIQUE,
                        "CORTEX_PLANNER": NodeRole.PLANNER,
                        "HUMAN_ORACLE": NodeRole.HUMAN_DECISION,
                    }
                    role = role_map.get(role_str, NodeRole.DIVERGE)

                    ptype_str = str(payload.get("payload_type", "CODE_DIFF"))
                    ptype = PayloadType(ptype_str) if ptype_str in PayloadType.__members__ else PayloadType.CODE_DIFF

                    node = SSTNode(
                        node_id=node_id,
                        parent_id=parent_id,
                        tree_id=tree.tree_id,
                        depth=depth,
                        domain=tree.domain,
                        role=role,
                        title=str(payload.get("title", f"Node {node_id}")),
                        payload_type=ptype,
                        content=str(payload.get("content", payload.get("patch_diff", ""))),
                        model=str(payload.get("model_id", payload.get("model", ""))),
                        temperature=float(payload.get("temperature", 0.7)),
                        status=NodeStatus.UNEXPANDED,
                        metadata=dict(payload.get("metadata", {})),
                    )
                    tree.add_node(node)

                elif kind == EventKind.CANDIDATE_PATCHED:
                    if node_id and node_id in tree.nodes:
                        tree.nodes[node_id].content = str(
                            payload.get("patch_diff", payload.get("content", tree.nodes[node_id].content))
                        )

                elif kind == EventKind.VERIFIER_STARTED:
                    if node_id and node_id in tree.nodes:
                        tree.nodes[node_id].status = NodeStatus.EVALUATING

                elif kind == EventKind.VERIFIER_FINISHED:
                    if node_id and node_id in tree.nodes:
                        passed = bool(payload.get("passed", False))
                        status = NodeStatus.PASS_DETERMINISTIC if passed else NodeStatus.FAIL_DETERMINISTIC
                        det_result = DeterministicGateResult(
                            passed=passed,
                            exit_code=int(payload.get("exit_code", 0)),
                            stdout=str(payload.get("stdout", "")),
                            stderr=str(payload.get("stderr", "")),
                            duration_seconds=float(payload.get("duration_seconds", 0.0)),
                            metrics=dict(payload.get("metrics", {})),
                            failure_reason=payload.get("failure_reason"),
                        )
                        tree.nodes[node_id].status = status
                        tree.nodes[node_id].deterministic_result = det_result

                        if not passed:
                            if node_id in tree.active_frontier:
                                tree.active_frontier.remove(node_id)
                            if node_id not in tree.pruned_nodes:
                                tree.pruned_nodes.append(node_id)

                elif kind == EventKind.SCORE_RECORDED:
                    if node_id and node_id in tree.nodes:
                        val_score = min(1.0, max(0.0, float(payload.get("value_score", 0.0))))
                        arch_fit = min(1.0, max(0.0, float(payload.get("architectural_fit", 0.0))))
                        verdict = str(payload.get("verdict", "APPROVE" if val_score >= 0.7 else "PRUNE"))
                        critique = str(payload.get("critique", ""))
                        cortex_eval = CortexEvaluation(
                            verdict=verdict,
                            value_score=val_score,
                            architectural_fit=arch_fit,
                            critique=critique,
                            synthesis_hints=list(payload.get("synthesis_hints", [])),
                        )
                        tree.nodes[node_id].cortex_evaluation = cortex_eval
                        tree.nodes[node_id].uct_score = float(payload.get("uct_score", val_score))

                        # Verifier failure cannot be overridden by subsequent score event
                        if tree.nodes[node_id].status != NodeStatus.FAIL_DETERMINISTIC:
                            if verdict == "APPROVE":
                                tree.nodes[node_id].status = NodeStatus.APPROVED_CORTEX
                            elif verdict == "PRUNE":
                                tree.nodes[node_id].status = NodeStatus.PRUNED_SEMANTIC
                                if node_id in tree.active_frontier:
                                    tree.active_frontier.remove(node_id)
                                if node_id not in tree.pruned_nodes:
                                    tree.pruned_nodes.append(node_id)

                elif kind == EventKind.NODE_PRUNED:
                    if node_id and node_id in tree.nodes:
                        tree.nodes[node_id].status = NodeStatus.PRUNED_SEMANTIC
                        tree.nodes[node_id].prune_reason = str(payload.get("reason", ""))
                        if node_id in tree.active_frontier:
                            tree.active_frontier.remove(node_id)
                        if node_id not in tree.pruned_nodes:
                            tree.pruned_nodes.append(node_id)

                elif kind == EventKind.SYNTHESIS_PROPOSED:
                    if node_id:
                        parent_ids = list(payload.get("parent_ids", []))
                        primary_parent_id = (
                            parent_ids[0] if parent_ids else str(payload.get("parent_id", tree.root_node_id))
                        )
                        parent_node = tree.nodes.get(primary_parent_id)
                        depth = (parent_node.depth + 1) if parent_node else 1

                        meta = dict(payload.get("metadata", {}))
                        if parent_ids:
                            meta["parent_ids"] = parent_ids
                        if "rationale" in payload:
                            meta["synthesis_rationale"] = payload["rationale"]

                        if node_id in tree.nodes:
                            tree.nodes[node_id].status = NodeStatus.SYNTHESIZED
                            if "patch_diff" in payload:
                                tree.nodes[node_id].content = str(payload["patch_diff"])
                            tree.nodes[node_id].metadata.update(meta)
                        else:
                            node = SSTNode(
                                node_id=node_id,
                                parent_id=primary_parent_id,
                                tree_id=tree.tree_id,
                                depth=depth,
                                domain=tree.domain,
                                role=NodeRole.SYNTHESIZE,
                                title=str(payload.get("title", f"Synthesized {node_id}")),
                                payload_type=PayloadType.SYNTHESIS,
                                content=str(payload.get("content", payload.get("patch_diff", ""))),
                                model=str(payload.get("model_id", payload.get("model", ""))),
                                temperature=float(payload.get("temperature", 0.3)),
                                status=NodeStatus.SYNTHESIZED,
                                metadata=meta,
                            )
                            tree.add_node(node)

                elif kind == EventKind.NODE_SELECTED:
                    if node_id:
                        if node_id not in tree.winning_path:
                            tree.winning_path.append(node_id)

                elif kind in {
                    EventKind.PROVIDER_ERROR,
                    EventKind.SEARCH_COMPLETED,
                    EventKind.SEARCH_CANCELLED,
                    EventKind.BUDGET_EXHAUSTED,
                    EventKind.VERIFIER_UNAVAILABLE,
                    EventKind.POLICY_VIOLATION,
                    EventKind.OUTCOME_REPORTED,
                }:
                    # Observability-only events: failure/budget/termination/
                    # outcome visibility with no DAG mutation. Domain outcome
                    # verdicts are recorded verbatim and must never mutate
                    # node state or satisfy promotion gates.
                    pass

                elif kind == EventKind.HUMAN_DECISION_RECORDED:
                    if node_id and node_id in tree.nodes:
                        verdict = str(payload.get("verdict", ""))
                        if verdict == "APPROVED":
                            tree.nodes[node_id].status = NodeStatus.APPROVED_CORTEX
                        elif verdict == "REJECTED":
                            tree.nodes[node_id].status = NodeStatus.REJECTED_HUMAN
                            if node_id in tree.active_frontier:
                                tree.active_frontier.remove(node_id)
                            if node_id not in tree.pruned_nodes:
                                tree.pruned_nodes.append(node_id)

                elif kind in {EventKind.PROMOTION_RECOMMENDED, EventKind.PROMOTION_RECORDED}:
                    champ_id = payload.get("champion_node_id", node_id)
                    if champ_id and champ_id in tree.nodes:
                        path: list[str] = []
                        curr: str | None = champ_id
                        while curr and curr in tree.nodes:
                            path.append(curr)
                            curr = tree.nodes[curr].parent_id
                        if tree.root_node_id not in path:
                            path.append(tree.root_node_id)
                        tree.winning_path = list(reversed(path))

        if tree is None:
            # Fallback if no TREE_CREATED event was found
            tid = initial_tree_id or "empty_tree"
            tree = SSTTree(
                tree_id=tid,
                domain=DomainMode.AUTOBUILD,
                root_goal="Empty",
                root_node_id=f"root_{tid}",
            )
        return tree
