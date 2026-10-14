"""Unit tests for SST Contracts, Events, Event Sourcing, and DAG Projection."""

from __future__ import annotations

from pathlib import Path

import pytest

from sst.core.contracts import CandidateProposal, ScoreBreakdown, TaskPacket
from sst.core.events import EventKind, SSTEvent
from sst.core.models import NodeStatus
from sst.storage.store import SQLiteSSTStore


def test_task_packet_frozen_and_hash_sensitivity() -> None:
    packet1 = TaskPacket(
        task_id="task_123",
        goal="Implement rate limiter",
        source_repo_root="/src/repo",
        base_commit="abcdef123456",
        snapshot_hash="hash_999",
        allowed_paths=["src/limiter.py"],
        forbidden_paths=["src/secret.py"],
        invariants=["No memory leaks"],
        acceptance_commands=["pytest tests/test_limiter.py"],
    )

    from pydantic import ValidationError

    # Immutability check: modifying attributes should fail
    with pytest.raises(ValidationError):
        packet1.goal = "Changed goal"

    digest1 = packet1.compute_hash()
    assert isinstance(digest1, str)
    assert len(digest1) == 64
    assert digest1 == packet1.compute_hash()

    # Changing forbidden_paths must change hash
    packet_forbid = TaskPacket(
        task_id="task_123",
        goal="Implement rate limiter",
        source_repo_root="/src/repo",
        base_commit="abcdef123456",
        snapshot_hash="hash_999",
        allowed_paths=["src/limiter.py"],
        forbidden_paths=["src/other_secret.py"],
        invariants=["No memory leaks"],
        acceptance_commands=["pytest tests/test_limiter.py"],
    )
    assert packet_forbid.compute_hash() != digest1

    # Changing acceptance_commands must change hash
    packet_cmd = TaskPacket(
        task_id="task_123",
        goal="Implement rate limiter",
        source_repo_root="/src/repo",
        base_commit="abcdef123456",
        snapshot_hash="hash_999",
        allowed_paths=["src/limiter.py"],
        forbidden_paths=["src/secret.py"],
        invariants=["No memory leaks"],
        acceptance_commands=["pytest tests/test_other.py"],
    )
    assert packet_cmd.compute_hash() != digest1


def test_candidate_proposal_contract() -> None:
    proposal = CandidateProposal(
        candidate_id="cand_1",
        tree_id="tree_1",
        parent_ids=["root_tree_1"],
        role="DIVERGE",
        title="Token Bucket Algorithm",
        rationale="O(1) token consumption with lock-free atomics",
        target_paths=["src/limiter.py"],
        patch_diff="--- a/src/limiter.py\n+++ b/src/limiter.py\n@@ ... @@",
    )
    assert proposal.primary_parent_id == "root_tree_1"
    assert proposal.role == "DIVERGE"


def test_score_breakdown_contract() -> None:
    score = ScoreBreakdown(
        passed_hard_gates=True,
        hard_gates={"syntax": True, "lint": True, "tests": True, "scope": True},
        soft_scores={"value_score": 0.95, "architectural_fit": 0.90},
        normalized_reward=0.925,
        critic_verdict="APPROVE",
        critic_rationale="Meets all requirements cleanly",
    )
    assert score.passed_hard_gates is True
    assert score.normalized_reward == 0.925


def test_event_store_append_and_idempotency(tmp_path: Path) -> None:
    db_path = tmp_path / "sst.db"
    store = SQLiteSSTStore(db_path)

    evt1 = SSTEvent(
        event_id="evt_01",
        tree_id="tree_abc",
        kind=EventKind.TREE_CREATED,
        idempotency_key="create_tree_abc",
        payload={"tree_id": "tree_abc", "root_goal": "Optimize cache", "domain": "AUTOBUILD"},
    )

    seq1 = store.append_event(evt1)
    assert seq1 == 1

    # Idempotent append should return the same sequence ID
    seq2 = store.append_event(evt1)
    assert seq2 == seq1

    events = store.get_events("tree_abc")
    assert len(events) == 1
    assert events[0].event_id == "evt_01"
    assert events[0].kind == EventKind.TREE_CREATED


def test_event_store_leases(tmp_path: Path) -> None:
    db_path = tmp_path / "sst_lease.db"
    store = SQLiteSSTStore(db_path)

    assert store.acquire_lease("tree_1", owner="worker_A", ttl_seconds=60) is True
    # Second owner should be rejected
    assert store.acquire_lease("tree_1", owner="worker_B", ttl_seconds=60) is False
    # Same owner can extend lease
    assert store.acquire_lease("tree_1", owner="worker_A", ttl_seconds=120) is True

    store.release_lease("tree_1", owner="worker_A")
    # Now worker B can acquire
    assert store.acquire_lease("tree_1", owner="worker_B", ttl_seconds=60) is True


def test_deterministic_dag_replay(tmp_path: Path) -> None:
    db_path = tmp_path / "sst_replay.db"
    store = SQLiteSSTStore(db_path)

    events = [
        SSTEvent(
            event_id="e1",
            tree_id="tree_mcts",
            kind=EventKind.TREE_CREATED,
            idempotency_key="k1",
            payload={
                "tree_id": "tree_mcts",
                "root_goal": "Build parser",
                "domain": "AUTOBUILD",
                "root_node_id": "root_mcts",
            },
        ),
        SSTEvent(
            event_id="e2",
            tree_id="tree_mcts",
            node_id="node_diverge_1",
            kind=EventKind.NODE_PROPOSED,
            idempotency_key="k2",
            payload={"parent_id": "root_mcts", "role": "DIVERGE", "title": "Recursive Descent", "patch_diff": "diff 1"},
        ),
        SSTEvent(
            event_id="e3",
            tree_id="tree_mcts",
            node_id="node_diverge_1",
            kind=EventKind.VERIFIER_STARTED,
            idempotency_key="k3",
            payload={},
        ),
        SSTEvent(
            event_id="e4",
            tree_id="tree_mcts",
            node_id="node_diverge_1",
            kind=EventKind.VERIFIER_FINISHED,
            idempotency_key="k4",
            payload={"passed": True, "exit_code": 0, "duration_seconds": 1.2},
        ),
        SSTEvent(
            event_id="e5",
            tree_id="tree_mcts",
            node_id="node_diverge_1",
            kind=EventKind.SCORE_RECORDED,
            idempotency_key="k5",
            payload={"value_score": 0.94, "verdict": "APPROVE", "critique": "Solid approach"},
        ),
        SSTEvent(
            event_id="e6",
            tree_id="tree_mcts",
            node_id="node_diverge_1",
            kind=EventKind.PROMOTION_RECORDED,
            idempotency_key="k6",
            payload={"champion_node_id": "node_diverge_1"},
        ),
    ]

    for e in events:
        store.append_event(e)

    tree = store.rebuild_tree_from_events("tree_mcts")
    assert tree is not None
    assert tree.root_goal == "Build parser"
    assert len(tree.nodes) == 2
    assert "node_diverge_1" in tree.nodes
    assert tree.nodes["node_diverge_1"].status == NodeStatus.APPROVED_CORTEX
    assert tree.nodes["node_diverge_1"].cortex_evaluation is not None
    assert tree.nodes["node_diverge_1"].cortex_evaluation.value_score == 0.94


def test_dag_replay_verifier_failure_cannot_be_overridden_by_score(tmp_path: Path) -> None:
    db_path = tmp_path / "sst_replay_fail.db"
    store = SQLiteSSTStore(db_path)

    events = [
        SSTEvent(
            event_id="e1",
            tree_id="t_fail",
            kind=EventKind.TREE_CREATED,
            idempotency_key="k1",
            payload={"tree_id": "t_fail", "root_goal": "Goal", "domain": "AUTOBUILD", "root_node_id": "root_f"},
        ),
        SSTEvent(
            event_id="e2",
            tree_id="t_fail",
            node_id="node_bad",
            kind=EventKind.NODE_PROPOSED,
            idempotency_key="k2",
            payload={"parent_id": "root_f", "role": "DIVERGE", "title": "Bad node"},
        ),
        SSTEvent(
            event_id="e3",
            tree_id="t_fail",
            node_id="node_bad",
            kind=EventKind.VERIFIER_FINISHED,
            idempotency_key="k3",
            payload={"passed": False, "exit_code": 1, "failure_reason": "Syntax error"},
        ),
        # Malicious or buggy score event with verdict APPROVE
        SSTEvent(
            event_id="e4",
            tree_id="t_fail",
            node_id="node_bad",
            kind=EventKind.SCORE_RECORDED,
            idempotency_key="k4",
            payload={"value_score": 0.99, "verdict": "APPROVE", "critique": "Attempting override"},
        ),
    ]

    for e in events:
        store.append_event(e)

    tree = store.rebuild_tree_from_events("t_fail")
    assert tree is not None
    bad_node = tree.nodes["node_bad"]
    assert bad_node.status != NodeStatus.APPROVED_CORTEX
    assert bad_node.status == NodeStatus.FAIL_DETERMINISTIC


def test_dag_replay_synthesis_and_promotion_lineage(tmp_path: Path) -> None:
    """Verifies that SYNTHESIS_PROPOSED nodes are created and PROMOTION_RECOMMENDED traces winning path."""
    store = SQLiteSSTStore(tmp_path / "test_synth_dag.db")
    events = [
        SSTEvent(
            event_id="e1",
            tree_id="t_synth",
            kind=EventKind.TREE_CREATED,
            idempotency_key="k1",
            payload={"tree_id": "t_synth", "root_goal": "Optimize parsing", "root_node_id": "root_01"},
        ),
        SSTEvent(
            event_id="e2",
            tree_id="t_synth",
            node_id="cand_a",
            kind=EventKind.NODE_PROPOSED,
            idempotency_key="k2",
            payload={"parent_id": "root_01", "title": "Strategy A", "patch_diff": "diff_a"},
        ),
        SSTEvent(
            event_id="e3",
            tree_id="t_synth",
            node_id="cand_b",
            kind=EventKind.NODE_PROPOSED,
            idempotency_key="k3",
            payload={"parent_id": "root_01", "title": "Strategy B", "patch_diff": "diff_b"},
        ),
        SSTEvent(
            event_id="e4",
            tree_id="t_synth",
            node_id="cand_synth",
            kind=EventKind.SYNTHESIS_PROPOSED,
            idempotency_key="k4",
            payload={
                "parent_ids": ["cand_a", "cand_b"],
                "title": "Synthesized A+B",
                "patch_diff": "diff_synth",
                "rationale": "Combined features",
            },
        ),
        SSTEvent(
            event_id="e5",
            tree_id="t_synth",
            node_id="cand_synth",
            kind=EventKind.VERIFIER_FINISHED,
            idempotency_key="k5",
            payload={"passed": True, "exit_code": 0},
        ),
        SSTEvent(
            event_id="e6",
            tree_id="t_synth",
            node_id="cand_synth",
            kind=EventKind.SCORE_RECORDED,
            idempotency_key="k6",
            payload={"value_score": 0.97, "verdict": "APPROVE"},
        ),
        SSTEvent(
            event_id="e7",
            tree_id="t_synth",
            node_id="cand_synth",
            kind=EventKind.PROMOTION_RECOMMENDED,
            idempotency_key="k7",
            payload={"champion_node_id": "cand_synth", "score": 0.97},
        ),
    ]

    for e in events:
        store.append_event(e)

    tree = store.rebuild_tree_from_events("t_synth")
    assert tree is not None
    assert "cand_synth" in tree.nodes
    synth_node = tree.nodes["cand_synth"]
    assert synth_node.status == NodeStatus.APPROVED_CORTEX
    assert synth_node.cortex_evaluation is not None
    assert synth_node.cortex_evaluation.value_score == 0.97
    assert synth_node.content == "diff_synth"
    assert synth_node.metadata.get("parent_ids") == ["cand_a", "cand_b"]

    # Winning path must trace lineage from root to champion
    assert tree.winning_path == ["root_01", "cand_a", "cand_synth"]
