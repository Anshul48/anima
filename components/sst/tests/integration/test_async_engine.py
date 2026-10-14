"""Tests for asynchronous parallel expansion and LLM backends in SSTEngine."""

import asyncio
import tempfile
from pathlib import Path

from sst.core.models import DomainMode
from sst.gateway.backends import SSTLLMClient
from sst.sandbox.evaluator import SSTDeterministicEvaluator
from sst.search.engine import SSTEngine
from sst.storage.store import SQLiteSSTStore


def test_async_expansion_with_llm_client() -> None:
    async def _run_test() -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "test_async_sst.db"
            store = SQLiteSSTStore(db_path)
            evaluator = SSTDeterministicEvaluator()
            engine = SSTEngine(
                domain=DomainMode.AUTOBUILD,
                workspace_dir=tmp_dir,
                store=store,
                evaluator=evaluator,
            )

            llm_client = SSTLLMClient(mock_mode=True)
            tree = engine.initialize_tree(root_goal="Implement Lock-Free Data Structures")

            candidate = engine.select_best_candidate(tree)
            assert candidate is not None

            # Execute async expansion
            children = await engine.execute_expansion_step_async(
                tree=tree,
                candidate_node=candidate,
                cheap_model=llm_client,
                frontier_model=llm_client,
            )

            assert len(children) >= 2
            for child in children:
                assert child.parent_id == candidate.node_id
                assert child.deterministic_result is not None
                assert child.deterministic_result.passed is True

            # Check backpropagation and winning path
            assert len(tree.winning_path) >= 2
            loaded = store.load_tree(tree.tree_id)
            assert loaded is not None
            assert len(loaded.nodes) >= 3

    asyncio.run(_run_test())
