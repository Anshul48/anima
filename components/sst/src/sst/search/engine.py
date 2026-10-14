"""Core State Space Tree (SST) MCTS Search Engine with AuDHD Dialectic Rollouts."""

from __future__ import annotations

import asyncio
import json
import math
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from sst.context.capsule import ContextCapsuleCompiler
from sst.core.models import (
    AuDHDContextCapsule,
    CortexEvaluation,
    DomainMode,
    NodeRole,
    NodeStatus,
    PayloadType,
    SSTNode,
    SSTTree,
)
from sst.gateway.backends import SSTLLMClient
from sst.prompts.dialectic import (
    render_adhd_explorer_prompt,
    render_asd_exploiter_prompt,
    render_cortex_critic_prompt,
    render_cortex_synthesizer_prompt,
)
from sst.sandbox.evaluator import SSTDeterministicEvaluator
from sst.storage.store import SQLiteSSTStore


class SSTEngine:
    """Orchestrates State Space Tree search with AuDHD exploration and heuristic pruning."""

    def __init__(
        self,
        domain: DomainMode,
        workspace_dir: Path | str,
        store: SQLiteSSTStore,
        evaluator: SSTDeterministicEvaluator | None = None,
        exploration_constant: float = 1.414,
        max_depth: int = 5,
        pruning_threshold: float = 0.70,
        rollout_batch_size: int = 3,
    ) -> None:
        self.domain = domain
        self.workspace_dir = Path(workspace_dir)
        self.store = store
        self.evaluator = evaluator or SSTDeterministicEvaluator()
        self.c = exploration_constant
        self.max_depth = max_depth
        self.pruning_threshold = pruning_threshold
        self.rollout_batch_size = rollout_batch_size
        self.capsule_compiler = ContextCapsuleCompiler(
            self.workspace_root if hasattr(self, "workspace_root") else self.workspace_dir
        )

    def initialize_tree(self, root_goal: str, initial_content: str = "") -> SSTTree:
        """Initializes a new State Space Tree with a root goal node."""
        tree_id = f"sst_{uuid.uuid4().hex[:12]}"
        root_node_id = f"node_{uuid.uuid4().hex[:8]}"

        root_node = SSTNode(
            node_id=root_node_id,
            parent_id=None,
            tree_id=tree_id,
            depth=0,
            domain=self.domain,
            role=NodeRole.CORTEX_PLANNER,
            title=f"Root Goal: {root_goal[:50]}",
            status=NodeStatus.APPROVED_CORTEX,
            payload_type=PayloadType.GOAL,
            content=initial_content or root_goal,
            visit_count=0,
            uct_score=1.0,
        )

        tree = SSTTree(
            tree_id=tree_id,
            domain=self.domain,
            root_goal=root_goal,
            root_node_id=root_node_id,
            nodes={root_node.node_id: root_node},
            active_frontier=[root_node.node_id],
            winning_path=[root_node.node_id],
        )

        self.store.save_tree(tree)
        return tree

    def select_best_candidate(self, tree: SSTTree) -> SSTNode | None:
        """Selects the best unexpanded or expandable node according to UCT formula."""
        eligible_nodes = [
            n
            for n in tree.nodes.values()
            if n.status in {NodeStatus.APPROVED_CORTEX, NodeStatus.PASS_DETERMINISTIC, NodeStatus.SYNTHESIZED}
            and n.depth < self.max_depth
        ]

        if not eligible_nodes:
            return None

        # Calculate UCT for all eligible nodes
        best_node: SSTNode | None = None
        best_score = -float("inf")

        for node in eligible_nodes:
            parent_visits = 1
            if node.parent_id and node.parent_id in tree.nodes:
                parent_visits = max(1, tree.nodes[node.parent_id].visit_count)

            exploitation = node.value_score
            exploration = self.c * math.sqrt(math.log(parent_visits + 1) / (node.visit_count + 1))
            uct = exploitation + exploration
            node.uct_score = uct

            if uct > best_score:
                best_score = uct
                best_node = node

        return best_node

    def _extract_failure_rationales(
        self,
        tree: SSTTree,
        negative_rules: list[str] | None = None,
    ) -> list[str]:
        """Extracts concrete prune reasons and negative rules rather than raw UUIDs."""
        rationales: list[str] = []

        # 1. Negative rules passed from caller or InsightsLedger
        if negative_rules:
            for r in negative_rules:
                if r and r not in rationales:
                    rationales.append(r)

        # 2. Extract prune reasons from pruned_nodes
        for nid in tree.pruned_nodes:
            node = tree.nodes.get(nid)
            if node:
                reason = node.prune_reason or (node.cortex_evaluation.critique if node.cortex_evaluation else None)
                if reason:
                    entry = f"{node.title}: {reason}"
                    if entry not in rationales:
                        rationales.append(entry)

        # 3. Check all nodes in tree with deterministic or semantic failure
        for node in tree.nodes.values():
            if node.status in {NodeStatus.FAIL_DETERMINISTIC, NodeStatus.PRUNED_SEMANTIC} and node.prune_reason:
                entry = f"{node.title}: {node.prune_reason}"
                if entry not in rationales:
                    rationales.append(entry)

        return rationales[-10:] if len(rationales) > 10 else rationales

    async def _generate_divergent_proposals(
        self,
        tree: SSTTree,
        capsule: AuDHDContextCapsule,
        cheap_model: SSTLLMClient | Callable[[str, float], str],
        negative_rules: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Generates high-entropy divergent proposals using ADHD prompt with distilled failure rationales."""
        prior_rationales = self._extract_failure_rationales(tree, negative_rules)

        adhd_prompt = render_adhd_explorer_prompt(
            goal=tree.root_goal,
            capsule=capsule,
            domain=self.domain,
            branch_count=self.rollout_batch_size,
            prior_attempts=prior_rationales,
        )

        if isinstance(cheap_model, SSTLLMClient):
            raw_adhd_resp = await cheap_model.generate_async(adhd_prompt, temperature=1.3)
        else:
            raw_adhd_resp = cheap_model(adhd_prompt, 1.3)

        return self._parse_json_branches(raw_adhd_resp)

    async def execute_expansion_step_async(
        self,
        tree: SSTTree,
        candidate_node: SSTNode,
        cheap_model: SSTLLMClient | Callable[[str, float], str],
        frontier_model: SSTLLMClient | Callable[[str], str],
        test_command: str | None = None,
        baseline_metrics: dict[str, float] | None = None,
        negative_rules: list[str] | None = None,
        target_files: list[str] | None = None,
    ) -> list[SSTNode]:
        """Asynchronously executes concurrent AuDHD dialectic rollouts, sandbox evaluation, and value pruning."""
        # Step 1: Compile Context Capsule
        resolved_targets = (
            target_files or candidate_node.metadata.get("target_files") or candidate_node.metadata.get("target_paths")
        )
        capsule = self.capsule_compiler.compile(
            goal=tree.root_goal,
            target_files=resolved_targets,
            invariants=candidate_node.metadata.get("invariants", []),
        )

        # Step 2: ADHD Explorer (High-Entropy Divergent Generation)
        branches = await self._generate_divergent_proposals(
            tree=tree,
            capsule=capsule,
            cheap_model=cheap_model,
            negative_rules=negative_rules,
        )

        # Step 3: ASD Exploiter Concurrent Refactoring & Deterministic Evaluation
        async def process_branch(idx: int, branch: dict[str, Any]) -> SSTNode:
            title = str(branch.get("strategy_title", f"Strategy {idx + 1}"))
            raw_content = str(branch.get("proposed_changes", ""))

            asd_prompt = render_asd_exploiter_prompt(
                parent_goal=tree.root_goal,
                mutation_title=title,
                mutation_content=raw_content,
                capsule=capsule,
                domain=self.domain,
            )

            if isinstance(cheap_model, SSTLLMClient):
                raw_asd_resp = await cheap_model.generate_async(asd_prompt, temperature=0.05)
            else:
                raw_asd_resp = cheap_model(asd_prompt, 0.05)

            parsed_asd = self._parse_json_dict(raw_asd_resp)
            clean_content = str(parsed_asd.get("executable_content", raw_content))
            clean_title = str(parsed_asd.get("refined_title", title))

            child_node = SSTNode(
                node_id=f"node_{uuid.uuid4().hex[:8]}",
                parent_id=candidate_node.node_id,
                tree_id=tree.tree_id,
                depth=candidate_node.depth + 1,
                domain=self.domain,
                role=NodeRole.ASD_EXPLOITER,
                title=clean_title,
                status=NodeStatus.EVALUATING,
                payload_type=PayloadType.CODE_DIFF
                if self.domain == DomainMode.AUTOBUILD
                else PayloadType.EXPERIMENT_TRIAL,
                content=clean_content,
                metadata={"refactoring_notes": parsed_asd.get("refactoring_notes", "")},
            )

            # Step 4: Deterministic Sandbox Gatekeeper
            det_result = await asyncio.to_thread(
                self.evaluator.evaluate,
                child_node,
                self.workspace_dir,
                test_command,
                baseline_metrics,
            )
            child_node.deterministic_result = det_result

            if not det_result.passed:
                child_node.status = NodeStatus.FAIL_DETERMINISTIC
                child_node.prune_reason = det_result.failure_reason or "Sandbox tests failed"
            else:
                child_node.status = NodeStatus.PASS_DETERMINISTIC

            tree.add_node(child_node)
            self.store.save_node(child_node)
            return child_node

        # Run all ASD branches concurrently
        generated_children: list[SSTNode] = list(
            await asyncio.gather(*[process_branch(idx, branch) for idx, branch in enumerate(branches)])
        )

        # Step 5: Frontier Value Critic & Semantic Synthesis
        surviving = [c for c in generated_children if c.status == NodeStatus.PASS_DETERMINISTIC]
        if surviving:
            critic_prompt = render_cortex_critic_prompt(
                goal=tree.root_goal,
                capsule=capsule,
                surviving_candidates=surviving,
                domain=self.domain,
            )

            if isinstance(frontier_model, SSTLLMClient):
                raw_critic_resp = await frontier_model.generate_async(critic_prompt, temperature=0.2)
            else:
                raw_critic_resp = frontier_model(critic_prompt)

            critic_data = self._parse_json_dict(raw_critic_resp)
            eval_list = critic_data.get("evaluations", [])

            for idx, item in enumerate(eval_list):
                n_id = item.get("node_id")
                target_node = next((n for n in surviving if n.node_id == n_id), None)
                if target_node is None and idx < len(surviving):
                    target_node = surviving[idx]

                if target_node:
                    cortex_eval = CortexEvaluation(
                        verdict=str(item.get("verdict", "APPROVE")),
                        value_score=float(item.get("value_score", 0.8)),
                        architectural_fit=float(item.get("architectural_fit", 0.8)),
                        critique=str(item.get("critique", "")),
                        synthesis_hints=list(item.get("synthesis_hints", [])),
                        human_escalation_reason=item.get("human_escalation_reason"),
                    )
                    target_node.cortex_evaluation = cortex_eval

                    if cortex_eval.verdict == "ESCALATE_HUMAN":
                        target_node.status = NodeStatus.AWAITING_HUMAN_ORACLE
                    elif cortex_eval.verdict == "PRUNE" or cortex_eval.value_score < self.pruning_threshold:
                        target_node.status = NodeStatus.PRUNED_SEMANTIC
                        target_node.prune_reason = cortex_eval.critique or "Low semantic value score"
                        if target_node.node_id in tree.active_frontier:
                            tree.active_frontier.remove(target_node.node_id)
                        if target_node.node_id not in tree.pruned_nodes:
                            tree.pruned_nodes.append(target_node.node_id)
                    else:
                        target_node.status = NodeStatus.APPROVED_CORTEX

                    self.store.save_node(target_node)

            # Step 6: Colimit Synthesis if recommended
            synthesis_opp = critic_data.get("synthesis_opportunity")
            if synthesis_opp and len(surviving) >= 2:
                synth_prompt = render_cortex_synthesizer_prompt(
                    goal=tree.root_goal,
                    capsule=capsule,
                    node_a=surviving[0],
                    node_b=surviving[1],
                    synthesis_guidance=str(synthesis_opp),
                )

                if isinstance(frontier_model, SSTLLMClient):
                    raw_synth_resp = await frontier_model.generate_async(synth_prompt, temperature=0.2)
                else:
                    raw_synth_resp = frontier_model(synth_prompt)

                synth_data = self._parse_json_dict(raw_synth_resp)

                synth_node = SSTNode(
                    node_id=f"node_{uuid.uuid4().hex[:8]}",
                    parent_id=candidate_node.node_id,
                    tree_id=tree.tree_id,
                    depth=candidate_node.depth + 1,
                    domain=self.domain,
                    role=NodeRole.CORTEX_CRITIC,
                    title=f"Synthesized: {synth_data.get('synthesized_title', 'Unified Branch')}",
                    status=NodeStatus.SYNTHESIZED,
                    payload_type=PayloadType.SYNTHESIS,
                    content=str(synth_data.get("executable_content", "")),
                    metadata={"synthesis_rationale": synth_data.get("synthesis_rationale", "")},
                )
                det_res = await asyncio.to_thread(
                    self.evaluator.evaluate,
                    synth_node,
                    self.workspace_dir,
                    test_command,
                    baseline_metrics,
                )
                synth_node.deterministic_result = det_res
                if not det_res.passed:
                    synth_node.status = NodeStatus.FAIL_DETERMINISTIC
                    synth_node.prune_reason = det_res.failure_reason
                tree.add_node(synth_node)
                self.store.save_node(synth_node)
                generated_children.append(synth_node)

        # Step 7: Backpropagation & Update Winning Path
        self._backpropagate(tree, candidate_node)
        self.store.save_tree(tree)
        return generated_children

    def execute_expansion_step(
        self,
        tree: SSTTree,
        candidate_node: SSTNode,
        cheap_model_fn: SSTLLMClient | Callable[[str, float], str],
        frontier_model_fn: SSTLLMClient | Callable[[str], str],
        test_command: str | None = None,
        baseline_metrics: dict[str, float] | None = None,
        negative_rules: list[str] | None = None,
        target_files: list[str] | None = None,
    ) -> list[SSTNode]:
        """Synchronous wrapper for execute_expansion_step_async."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor() as pool:
                return pool.submit(
                    asyncio.run,
                    self.execute_expansion_step_async(
                        tree,
                        candidate_node,
                        cheap_model_fn,
                        frontier_model_fn,
                        test_command,
                        baseline_metrics,
                        negative_rules,
                        target_files,
                    ),
                ).result()
        else:
            return asyncio.run(
                self.execute_expansion_step_async(
                    tree,
                    candidate_node,
                    cheap_model_fn,
                    frontier_model_fn,
                    test_command,
                    baseline_metrics,
                    negative_rules,
                    target_files,
                )
            )

    def _backpropagate(self, tree: SSTTree, leaf: SSTNode) -> None:
        """Propagates updated value and visit metrics upwards to the root."""
        curr: SSTNode | None = leaf
        while curr:
            curr.visit_count += 1
            children = tree.get_children(curr.node_id)
            if children:
                best_val = max((c.value_score for c in children), default=0.0)
                if curr.cortex_evaluation:
                    curr.cortex_evaluation.value_score = max(curr.cortex_evaluation.value_score, best_val)
            self.store.save_node(curr)
            curr = tree.nodes.get(curr.parent_id) if curr.parent_id else None

        # Update winning path (highest value trajectory from root)
        path = [tree.root_node_id]
        curr_id = tree.root_node_id
        while True:
            children = tree.get_children(curr_id)
            approved = [
                c
                for c in children
                if c.status in {NodeStatus.APPROVED_CORTEX, NodeStatus.SYNTHESIZED, NodeStatus.PASS_DETERMINISTIC}
            ]
            if not approved:
                break
            best_child = max(approved, key=lambda c: c.value_score)
            path.append(best_child.node_id)
            curr_id = best_child.node_id

        tree.winning_path = path

    def _parse_json_branches(self, raw_text: str) -> list[dict[str, Any]]:
        data = self._parse_json_dict(raw_text)
        branches = data.get("branches", [])
        return branches if isinstance(branches, list) else []

    def _parse_json_dict(self, raw_text: str) -> dict[str, Any]:
        raw_text = raw_text.strip()
        if "```json" in raw_text:
            raw_text = raw_text.split("```json", 1)[1].split("```", 1)[0].strip()
        elif "```" in raw_text:
            raw_text = raw_text.split("```", 1)[1].split("```", 1)[0].strip()
        try:
            res = json.loads(raw_text)
            return res if isinstance(res, dict) else {}
        except Exception:
            return {}
