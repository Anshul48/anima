"""Tests for SST and AuDHD core models."""

from __future__ import annotations

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


def test_sst_node_creation_and_value_score() -> None:
    node = SSTNode(
        node_id="node_001",
        tree_id="tree_001",
        domain=DomainMode.AUTOBUILD,
        role=NodeRole.ADHD_EXPLORER,
        title="Lock-Free Ring Buffer",
        payload_type=PayloadType.CODE_DIFF,
        content="class RingBuffer: pass",
    )
    assert node.status == NodeStatus.UNEXPANDED
    assert node.value_score == 0.0

    # Attach deterministic result
    node.deterministic_result = DeterministicGateResult(
        passed=True,
        exit_code=0,
        tests_passed=5,
    )
    assert node.value_score == 0.5

    # Attach cortex evaluation
    node.cortex_evaluation = CortexEvaluation(
        verdict="APPROVE",
        value_score=0.92,
        architectural_fit=0.95,
        critique="Excellent lock-free concurrency.",
    )
    assert node.value_score == 0.92


def test_sst_tree_frontier_management() -> None:
    tree = SSTTree(
        tree_id="tree_001",
        domain=DomainMode.AUTOBUILD,
        root_goal="Build fast cache",
        root_node_id="root_01",
    )
    root = SSTNode(
        node_id="root_01",
        tree_id="tree_001",
        domain=DomainMode.AUTOBUILD,
        role=NodeRole.CORTEX_PLANNER,
        title="Root",
        payload_type=PayloadType.GOAL,
        content="Cache goal",
    )
    tree.add_node(root)
    assert "root_01" in tree.active_frontier

    # Add child
    child = SSTNode(
        node_id="child_01",
        parent_id="root_01",
        tree_id="tree_001",
        domain=DomainMode.AUTOBUILD,
        role=NodeRole.ASD_EXPLOITER,
        title="Child 1",
        status=NodeStatus.FAIL_DETERMINISTIC,
        payload_type=PayloadType.CODE_DIFF,
        content="def broken(): pass",
    )
    tree.add_node(child)
    assert "child_01" not in tree.active_frontier
    assert "child_01" in tree.pruned_nodes
