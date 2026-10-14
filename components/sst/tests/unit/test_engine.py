"""Tests for SST MCTS Search Engine and AuDHD Dialectic Expansion."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from sst.core.models import (
    DomainMode,
    NodeRole,
    NodeStatus,
    PayloadType,
    SSTNode,
)
from sst.sandbox.evaluator import SSTDeterministicEvaluator
from sst.search.engine import SSTEngine
from sst.storage.store import SQLiteSSTStore


def test_sst_engine_expansion_and_pruning() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test_sst.db"
        store = SQLiteSSTStore(db_path)
        evaluator = SSTDeterministicEvaluator()
        engine = SSTEngine(
            domain=DomainMode.AUTOBUILD,
            workspace_dir=tmp_dir,
            store=store,
            evaluator=evaluator,
            pruning_threshold=0.75,
        )

        tree = engine.initialize_tree(root_goal="Implement concurrent map")
        assert tree.root_node_id in tree.nodes

        candidate = engine.select_best_candidate(tree)
        assert candidate is not None
        assert candidate.node_id == tree.root_node_id

        # Mock cheap worker that produces 2 branches: one valid, one invalid syntax
        def mock_cheap_worker(prompt: str, temp: float) -> str:
            if "ADHD EXPLORER" in prompt:
                return json.dumps(
                    {
                        "branches": [
                            {
                                "strategy_title": "Sharded Mutex Map",
                                "proposed_changes": "class ShardedMap:\n    def __init__(self):\n        self.shards = [{} for _ in range(16)]\n",
                            },
                            {
                                "strategy_title": "Broken Syntax Map",
                                "proposed_changes": "def broken(:\n    pass\n",
                            },
                        ]
                    }
                )
            else:  # ASD EXPLOITER
                if "Sharded Mutex Map" in prompt:
                    return json.dumps(
                        {
                            "refined_title": "Strict Sharded Map",
                            "refactoring_notes": "Type safety added",
                            "executable_content": "class ShardedMap:\n    def __init__(self):\n        self.shards = [{} for _ in range(16)]\n",
                        }
                    )
                else:
                    return json.dumps(
                        {
                            "refined_title": "Broken Syntax Map",
                            "refactoring_notes": "Unfixable",
                            "executable_content": "def broken(:\n    pass\n",
                        }
                    )

        def mock_frontier_critic(prompt: str) -> str:
            return json.dumps(
                {
                    "evaluations": [
                        {
                            "node_id": list(tree.nodes.keys())[-1],
                            "verdict": "APPROVE",
                            "value_score": 0.90,
                            "architectural_fit": 0.95,
                            "critique": "Solid partitioned design.",
                        }
                    ]
                }
            )

        children = engine.execute_expansion_step(
            tree=tree,
            candidate_node=candidate,
            cheap_model_fn=mock_cheap_worker,
            frontier_model_fn=mock_frontier_critic,
        )

        assert len(children) == 2
        # Broken branch must fail deterministic gate
        broken_node = next(c for c in children if "Broken" in c.title)
        assert broken_node.status == NodeStatus.FAIL_DETERMINISTIC

        # Valid branch passes deterministic gate
        valid_node = next(c for c in children if "Sharded" in c.title)
        assert valid_node.status == NodeStatus.APPROVED_CORTEX
        assert valid_node.deterministic_result is not None
        assert valid_node.deterministic_result.passed is True
        assert valid_node.value_score == 0.90

        # Verify tree state in DB
        loaded_tree = store.load_tree(tree.tree_id)
        assert loaded_tree is not None
        assert len(loaded_tree.nodes) == 3
        assert valid_node.node_id in loaded_tree.winning_path


def test_sst_engine_negative_rules_and_failure_rationales_injection() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test_sst2.db"
        store = SQLiteSSTStore(db_path)
        evaluator = SSTDeterministicEvaluator()
        engine = SSTEngine(
            domain=DomainMode.AUTORESEARCH,
            workspace_dir=tmp_dir,
            store=store,
            evaluator=evaluator,
        )

        tree = engine.initialize_tree(root_goal="Improve Transformer Decoding")
        candidate = engine.select_best_candidate(tree)
        assert candidate is not None

        failed_node = SSTNode(
            node_id="node_failed_01",
            parent_id=candidate.node_id,
            tree_id=tree.tree_id,
            depth=1,
            domain=DomainMode.AUTORESEARCH,
            role=NodeRole.ASD_EXPLOITER,
            title="Uniform KV Cache Eviction",
            status=NodeStatus.FAIL_DETERMINISTIC,
            payload_type=PayloadType.EXPERIMENT_TRIAL,
            content="print('failed')",
            prune_reason="Uniform eviction destroyed attention sinks and exploded perplexity.",
        )
        tree.add_node(failed_node)
        tree.pruned_nodes.append("node_failed_01")

        captured_prompts: list[str] = []

        def mock_cheap_worker(prompt: str, temp: float) -> str:
            captured_prompts.append(prompt)
            return json.dumps(
                {
                    "branches": [
                        {
                            "strategy_title": "Sink-Preserving Cache",
                            "proposed_changes": "import json\nprint(json.dumps({'accuracy': 0.88}))",
                        }
                    ]
                }
            )

        def mock_frontier_critic(prompt: str) -> str:
            return json.dumps(
                {
                    "evaluations": [
                        {
                            "node_id": "node_new",
                            "verdict": "APPROVE",
                            "value_score": 0.95,
                            "architectural_fit": 0.95,
                            "critique": "Optimal retention mechanism.",
                        }
                    ]
                }
            )

        custom_negative_rules = ["Never prune initial 4 attention sink tokens"]

        children = engine.execute_expansion_step(
            tree=tree,
            candidate_node=candidate,
            cheap_model_fn=mock_cheap_worker,
            frontier_model_fn=mock_frontier_critic,
            negative_rules=custom_negative_rules,
        )

        assert len(children) >= 1
        adhd_prompt = next(p for p in captured_prompts if "HIGH-ENTROPY RESEARCH EXPLORATION" in p)
        assert "Never prune initial 4 attention sink tokens" in adhd_prompt
        assert "Uniform KV Cache Eviction: Uniform eviction destroyed attention sinks" in adhd_prompt
        assert "node_failed_01" not in adhd_prompt.split("LEARNED NEGATIVE RULES")[1].split("PRIOR INSIGHTS")[0]


def test_sst_engine_backpropagate_visit_count_and_wal() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test_sst_wal.db"
        store = SQLiteSSTStore(db_path)

        # Verify WAL mode is set
        with store._connection() as conn:
            cur = conn.execute("PRAGMA journal_mode;")
            mode = cur.fetchone()[0]
            assert mode.lower() == "wal"

        engine = SSTEngine(
            domain=DomainMode.AUTOBUILD,
            workspace_dir=tmp_dir,
            store=store,
        )
        tree = engine.initialize_tree(root_goal="Backprop test")
        root_node = tree.nodes[tree.root_node_id]
        assert root_node.visit_count == 0

        child = SSTNode(
            node_id="child_node_1",
            parent_id=root_node.node_id,
            tree_id=tree.tree_id,
            depth=1,
            domain=DomainMode.AUTOBUILD,
            role=NodeRole.ASD_EXPLOITER,
            title="Child",
            payload_type=PayloadType.CODE_DIFF,
            content="print('child')",
            status=NodeStatus.APPROVED_CORTEX,
        )
        grandchild = SSTNode(
            node_id="grandchild_node_1",
            parent_id="child_node_1",
            tree_id=tree.tree_id,
            depth=2,
            domain=DomainMode.AUTOBUILD,
            role=NodeRole.ASD_EXPLOITER,
            title="Grandchild",
            payload_type=PayloadType.CODE_DIFF,
            content="print('grandchild')",
            status=NodeStatus.APPROVED_CORTEX,
        )
        tree.add_node(child)
        tree.add_node(grandchild)

        engine._backpropagate(tree, grandchild)

        assert grandchild.visit_count == 1
        assert child.visit_count == 1
        assert root_node.visit_count == 1
