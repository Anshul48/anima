"""Unit tests for Exact-Patch Candidate Custody, Path Traversal Defenses, and Verifier Sandboxes.

SYNTHETIC PROVENANCE: the "[REDACTED]" marker below is a synthetic
redaction-test placeholder, never a real credential.
"""

from __future__ import annotations

from pathlib import Path

from sst.core.contracts import CandidateProposal, TaskPacket
from sst.sandbox.custody import CandidateCustodyManager


def test_candidate_custody_path_traversal_rejection(tmp_path: Path) -> None:
    custody = CandidateCustodyManager(base_worktree_dir=tmp_path / "worktrees")
    proposal = CandidateProposal(
        candidate_id="cand_bad_path",
        tree_id="tree_1",
        title="Path traversal attack",
        rationale="Attempt escaping workspace",
        target_paths=["../../etc/passwd"],
        patch_diff="malicious content",
    )

    ws = tmp_path / "workspace"
    ws.mkdir()
    res = custody.apply_proposal(proposal, ws)
    assert res.success is False
    assert "Path Traversal Violation" in (res.error_message or "")


def test_candidate_custody_file_operations_path_traversal(tmp_path: Path) -> None:
    custody = CandidateCustodyManager(base_worktree_dir=tmp_path / "worktrees")
    proposal = CandidateProposal(
        candidate_id="cand_bad_file_ops",
        tree_id="tree_1",
        title="File op traversal attack",
        rationale="Attempt escaping workspace via file_operations",
        target_paths=[],
        file_operations=[{"path": "../escape.txt", "content": "malicious", "action": "write"}],
    )

    ws = tmp_path / "workspace"
    ws.mkdir()
    res = custody.apply_proposal(proposal, ws)
    assert res.success is False
    assert "Path Traversal Violation" in (res.error_message or "")
    assert not (tmp_path / "escape.txt").exists()


def test_candidate_custody_diff_header_path_traversal(tmp_path: Path) -> None:
    custody = CandidateCustodyManager(base_worktree_dir=tmp_path / "worktrees")
    diff_text = "--- a/../escape.txt\n+++ b/../escape.txt\n@@ -0,0 +1 @@\n+malicious\n"
    proposal = CandidateProposal(
        candidate_id="cand_bad_diff",
        tree_id="tree_1",
        title="Diff header traversal attack",
        rationale="Attempt escaping workspace via diff header",
        target_paths=[],
        patch_diff=diff_text,
    )

    ws = tmp_path / "workspace"
    ws.mkdir()
    res = custody.apply_proposal(proposal, ws)
    assert res.success is False
    assert "Path Traversal Violation" in (res.error_message or "")
    assert not (tmp_path / "escape.txt").exists()


def test_candidate_custody_secret_rejection(tmp_path: Path) -> None:
    custody = CandidateCustodyManager(base_worktree_dir=tmp_path / "worktrees")
    proposal = CandidateProposal(
        candidate_id="cand_secret",
        tree_id="tree_1",
        title="Secret leak",
        rationale="Embedding OpenAI secret",
        target_paths=["src/client.py"],
        patch_diff='API_KEY = "sk-123456789012345678901234567890"',
    )

    ws = tmp_path / "workspace"
    ws.mkdir()
    res = custody.apply_proposal(proposal, ws)
    assert res.success is False
    assert "Security Policy Violation" in (res.error_message or "")


def test_candidate_custody_forbidden_paths(tmp_path: Path) -> None:
    custody = CandidateCustodyManager(base_worktree_dir=tmp_path / "worktrees")
    task = TaskPacket(
        task_id="t1",
        goal="Fix bug",
        source_repo_root=str(tmp_path),
        base_commit="abc",
        snapshot_hash="h1",
        allowed_paths=["src/core"],
        forbidden_paths=["src/core/security.py"],
    )

    proposal = CandidateProposal(
        candidate_id="cand_forbidden",
        tree_id="tree_1",
        title="Modify security file",
        rationale="Change security config",
        target_paths=["src/core/security.py"],
        patch_diff="# update security",
    )

    ws = tmp_path / "workspace"
    ws.mkdir()
    res = custody.apply_proposal(proposal, ws, task=task)
    assert res.success is False
    assert "Scope Policy Violation" in (res.error_message or "")


def test_candidate_custody_apply_and_verify(tmp_path: Path) -> None:
    custody = CandidateCustodyManager(base_worktree_dir=tmp_path / "worktrees")
    src_dir = tmp_path / "src_repo"
    src_dir.mkdir()
    (src_dir / "math_lib.py").write_text("def add(a, b): return a - b\n", encoding="utf-8")
    (src_dir / "test_math.py").write_text("from math_lib import add\nassert add(2, 3) == 5\n", encoding="utf-8")

    task = TaskPacket(
        task_id="t_math",
        goal="Fix addition logic",
        source_repo_root=str(src_dir),
        base_commit="commit1",
        snapshot_hash="hash1",
        allowed_paths=["math_lib.py"],
        acceptance_commands=["python test_math.py"],
    )

    proposal = CandidateProposal(
        candidate_id="cand_fixed",
        tree_id="tree_math",
        title="Fix addition operator",
        rationale="Change subtraction to addition",
        target_paths=["math_lib.py"],
        patch_diff="def add(a, b): return a + b\n",
    )

    res = custody.verify_candidate_proposal(
        task=task,
        proposal=proposal,
        source_dir=src_dir,
    )

    assert res.passed is True
    assert res.exit_code == 0


def test_manual_unified_diff_preserves_unmodified_lines(tmp_path: Path) -> None:
    custody = CandidateCustodyManager(base_worktree_dir=tmp_path / "worktrees")
    ws = tmp_path / "workspace"
    ws.mkdir()
    target_file = ws / "module.py"
    initial_content = "line1\nline2\nline3\nline4\nline5\n"
    target_file.write_text(initial_content, encoding="utf-8")

    diff_text = "--- a/module.py\n+++ b/module.py\n@@ -2,3 +2,3 @@\n line2\n-line3\n+line3_modified\n line4\n"

    err = custody._apply_unified_diff_manually(diff_text, ws)
    assert err is None
    expected_content = "line1\nline2\nline3_modified\nline4\nline5\n"
    assert target_file.read_text(encoding="utf-8") == expected_content


def test_raw_code_payload_without_target_paths_rejected(tmp_path: Path) -> None:
    custody = CandidateCustodyManager(base_worktree_dir=tmp_path / "worktrees")
    ws = tmp_path / "workspace"
    ws.mkdir()

    proposal = CandidateProposal(
        candidate_id="cand_no_target",
        tree_id="tree_1",
        title="Raw code no target",
        rationale="Missing target path",
        target_paths=[],
        patch_diff="def foo(): pass\n",
    )

    res = custody.apply_proposal(proposal, ws)
    assert res.success is False
    assert "Target path required for raw code payload" in (res.error_message or "")


def test_cleanup_candidate_and_tree(tmp_path: Path) -> None:
    custody = CandidateCustodyManager(base_worktree_dir=tmp_path / "worktrees")
    src = tmp_path / "src"
    src.mkdir()
    (src / "file.txt").write_text("hello", encoding="utf-8")

    cand_ws = custody.create_candidate_workspace("tree_clean", "cand_1", src)
    assert cand_ws.exists()
    assert (cand_ws / "file.txt").exists()

    cand_ws_2 = custody.create_candidate_workspace("tree_clean", "cand_2", src)
    assert cand_ws_2.exists()

    custody.cleanup_candidate("tree_clean", "cand_1")
    assert not cand_ws.exists()
    assert cand_ws_2.exists()

    custody.cleanup_tree("tree_clean")
    assert not (tmp_path / "worktrees" / "tree_clean").exists()
