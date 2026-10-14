"""Tests for SQLite SST storage and visual DAG serializers."""

from __future__ import annotations

import tempfile
from pathlib import Path

from sst.core.models import (
    DomainMode,
    NodeRole,
    NodeStatus,
    PayloadType,
    SSTNode,
    SSTTree,
)
from sst.storage.serializer import serialize_sst_tree
from sst.storage.store import SQLiteSSTStore


def test_sst_store_and_serializer_roundtrip() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "sst_test.db"
        store = SQLiteSSTStore(db_path)

        tree = SSTTree(
            tree_id="tree_test_100",
            domain=DomainMode.AUTOBUILD,
            root_goal="Implement Raft Consensus",
            root_node_id="node_root",
        )
        root = SSTNode(
            node_id="node_root",
            tree_id="tree_test_100",
            domain=DomainMode.AUTOBUILD,
            role=NodeRole.CORTEX_PLANNER,
            title="Raft Goal",
            status=NodeStatus.APPROVED_CORTEX,
            payload_type=PayloadType.GOAL,
            content="Raft architecture spec",
        )
        child = SSTNode(
            node_id="node_child_1",
            parent_id="node_root",
            tree_id="tree_test_100",
            depth=1,
            domain=DomainMode.AUTOBUILD,
            role=NodeRole.ASD_EXPLOITER,
            title="Leader Election Implementation",
            status=NodeStatus.APPROVED_CORTEX,
            payload_type=PayloadType.CODE_DIFF,
            content="def start_election(): pass",
        )
        tree.add_node(root)
        tree.add_node(child)
        tree.winning_path = ["node_root", "node_child_1"]

        store.save_tree(tree)

        # Reload
        loaded = store.load_tree("tree_test_100")
        assert loaded is not None
        assert len(loaded.nodes) == 2
        assert loaded.winning_path == ["node_root", "node_child_1"]

        # Verify timestamp persistence
        assert loaded.created_at == tree.created_at
        assert loaded.nodes["node_root"].created_at == root.created_at
        assert loaded.nodes["node_child_1"].created_at == child.created_at

        # Serialize for UI
        graph_data = serialize_sst_tree(loaded)
        assert graph_data["treeId"] == "tree_test_100"
        assert len(graph_data["nodes"]) == 2
        assert len(graph_data["edges"]) == 1
        assert graph_data["edges"][0]["source"] == "node_root"
        assert graph_data["edges"][0]["target"] == "node_child_1"


def test_serializer_multi_parent_synthesis_edges() -> None:
    """Verifies that serialize_sst_tree emits edges for all synthesis parent branches."""
    tree = SSTTree(
        tree_id="tree_synth_ser",
        domain=DomainMode.AUTOBUILD,
        root_goal="Merge branches",
        root_node_id="r",
    )
    r = SSTNode(
        node_id="r",
        tree_id="tree_synth_ser",
        domain=DomainMode.AUTOBUILD,
        role=NodeRole.PLANNER,
        title="Root",
        payload_type=PayloadType.GOAL,
        content="Goal",
        status=NodeStatus.APPROVED_CORTEX,
    )
    b1 = SSTNode(
        node_id="b1",
        parent_id="r",
        tree_id="tree_synth_ser",
        depth=1,
        domain=DomainMode.AUTOBUILD,
        role=NodeRole.DIVERGE,
        title="B1",
        payload_type=PayloadType.CODE_DIFF,
        content="b1",
        status=NodeStatus.PASS_DETERMINISTIC,
    )
    b2 = SSTNode(
        node_id="b2",
        parent_id="r",
        tree_id="tree_synth_ser",
        depth=1,
        domain=DomainMode.AUTOBUILD,
        role=NodeRole.REFINE,
        title="B2",
        payload_type=PayloadType.CODE_DIFF,
        content="b2",
        status=NodeStatus.PASS_DETERMINISTIC,
    )
    synth = SSTNode(
        node_id="s",
        parent_id="b1",
        tree_id="tree_synth_ser",
        depth=2,
        domain=DomainMode.AUTOBUILD,
        role=NodeRole.SYNTHESIZE,
        title="Synth",
        payload_type=PayloadType.SYNTHESIS,
        content="synth",
        status=NodeStatus.SYNTHESIZED,
        metadata={"parent_ids": ["b1", "b2"]},
    )
    tree.add_node(r)
    tree.add_node(b1)
    tree.add_node(b2)
    tree.add_node(synth)

    graph_data = serialize_sst_tree(tree)
    assert len(graph_data["nodes"]) == 4
    assert len(graph_data["edges"]) == 4
    synth_edges = [e for e in graph_data["edges"] if e["target"] == "s"]
    assert len(synth_edges) == 2
    sources = {e["source"] for e in synth_edges}
    assert sources == {"b1", "b2"}
    assert all(e["type"] == "SYNTHESIS" for e in synth_edges)
