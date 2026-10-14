"""AuDHD State Space Tree (SST) Search Runner for autonomous code synthesis tasks."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sst.core.contracts import CandidateProposal
from sst.core.models import DomainMode, NodeStatus, SSTNode, SSTTree
from sst.gateway.backends import SSTLLMClient
from sst.sandbox.custody import CandidateCustodyManager
from sst.sandbox.evaluator import SSTDeterministicEvaluator
from sst.search.engine import SSTEngine
from sst.storage.store import SQLiteSSTStore


class SSTBuildRunner:
    """Executes high-entropy AuDHD State Space Tree code generation and pruning."""

    def __init__(
        self,
        workspace_dir: Path | str,
        config: Any | None = None,
        db_path: Path | str | None = None,
        cheap_model: str = "qwen-2.5-coder-32b",
        frontier_model: str = "glm-5",
        mock_mode: bool = False,
    ) -> None:
        self.workspace_dir = Path(workspace_dir)
        self.config = config
        db = Path(db_path) if db_path else self.workspace_dir / ".sst" / "sst_build.db"
        self.store = SQLiteSSTStore(db)
        self.evaluator = SSTDeterministicEvaluator()
        self.engine = SSTEngine(
            domain=DomainMode.AUTOBUILD,
            workspace_dir=self.workspace_dir,
            store=self.store,
            evaluator=self.evaluator,
            pruning_threshold=0.70,
            rollout_batch_size=3,
        )
        self.llm_client = SSTLLMClient(
            cheap_model=cheap_model,
            frontier_model=frontier_model,
            mock_mode=mock_mode,
        )

    def execute_build_goal(
        self,
        goal: str,
        target_files: list[str] | None = None,
        test_command: str | None = None,
        max_iterations: int = 3,
    ) -> SSTTree:
        """Runs the MCTS AuDHD search loop over the codebase task."""
        tree = self.engine.initialize_tree(root_goal=goal)

        for _ in range(max_iterations):
            candidate = self.engine.select_best_candidate(tree)
            if not candidate:
                break

            self.engine.execute_expansion_step(
                tree=tree,
                candidate_node=candidate,
                cheap_model_fn=self.llm_client,
                frontier_model_fn=self.llm_client,
                test_command=test_command,
                target_files=target_files,
            )

        # Apply winning path code to the workspace if approved through custody
        winning_node_ids = [nid for nid in tree.winning_path if nid != tree.root_node_id]
        if winning_node_ids:
            champion = tree.nodes.get(winning_node_ids[-1])
            if champion and champion.status in {
                NodeStatus.APPROVED_CORTEX,
                NodeStatus.SYNTHESIZED,
                NodeStatus.PASS_DETERMINISTIC,
            }:
                self._apply_champion_to_workspace(champion, target_files)

        return tree

    def _apply_champion_to_workspace(self, node: SSTNode, target_files: list[str] | None) -> None:
        """Applies winning code changes safely to workspace using custody path containment."""
        content = node.content.strip()
        if "```python" in content:
            content = content.split("```python", 1)[1].split("```", 1)[0].strip()
        elif "```" in content:
            content = content.split("```", 1)[1].split("```", 1)[0].strip()

        target = target_files[0] if target_files else "solution.py"
        custody = CandidateCustodyManager()
        proposal = CandidateProposal(
            candidate_id=node.node_id,
            tree_id=node.tree_id,
            title=node.title,
            rationale="Champion proposal",
            target_paths=[target],
            patch_diff=content,
        )
        res = custody.apply_proposal(proposal, self.workspace_dir)
        if not res.success:
            raise RuntimeError(f"Failed to apply champion to workspace: {res.error_message}")
