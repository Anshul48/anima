"""Unit tests for SST CLI status, human decisions, promotion, and visualization export."""

import subprocess
from pathlib import Path

from click.testing import CliRunner

from sst.cli.main import cli
from sst.core.events import EventKind, SSTEvent
from sst.storage.store import SQLiteSSTStore


def test_sst_cli_status_decide_and_promote(tmp_path: Path) -> None:
    db_dir = tmp_path / ".sst"
    db_dir.mkdir(parents=True, exist_ok=True)
    tree_id = "tree_sample_99"
    store = SQLiteSSTStore(db_dir / f"{tree_id}.db")

    # Seed events
    events = [
        SSTEvent(
            event_id="e1",
            tree_id=tree_id,
            kind=EventKind.TREE_CREATED,
            idempotency_key="k1",
            payload={
                "tree_id": tree_id,
                "root_goal": "Implement greeting function",
                "base_commit": "non_git_workspace",
                "root_node_id": f"root_{tree_id}",
            },
        ),
        SSTEvent(
            event_id="e2",
            tree_id=tree_id,
            node_id="cand_hello",
            kind=EventKind.NODE_PROPOSED,
            idempotency_key="k2",
            payload={
                "parent_id": f"root_{tree_id}",
                "role": "DIVERGE",
                "title": "Hello world implementation",
                "target_paths": ["greet.py"],
                "patch_diff": "def greet(): return 'hello world'\n",
            },
        ),
        SSTEvent(
            event_id="e3",
            tree_id=tree_id,
            node_id="cand_hello",
            kind=EventKind.VERIFIER_FINISHED,
            idempotency_key="k3",
            payload={
                "passed": True,
                "patch_hash": "2dfcd2211d13006611bee0301f89df73f105433dbd94745c77749caf804e3472",
                "exit_code": 0,
                "duration_seconds": 0.5,
            },
        ),
        SSTEvent(
            event_id="e4",
            tree_id=tree_id,
            node_id="cand_hello",
            kind=EventKind.SCORE_RECORDED,
            idempotency_key="k4",
            payload={"value_score": 0.95, "verdict": "APPROVE"},
        ),
        SSTEvent(
            event_id="e5",
            tree_id=tree_id,
            node_id="cand_hello",
            kind=EventKind.PROMOTION_RECOMMENDED,
            idempotency_key="k5",
            payload={"champion_node_id": "cand_hello"},
        ),
    ]

    for e in events:
        store.append_event(e)

    runner = CliRunner()

    # 1. Test status command
    res_st = runner.invoke(cli, ["status", tree_id, "--project-path", str(tmp_path)])
    assert res_st.exit_code == 0
    assert "cand_hello" in res_st.output

    # 2. Test decide command
    res_dec = runner.invoke(
        cli,
        [
            "decide",
            tree_id,
            "cand_hello",
            "--verdict",
            "APPROVED",
            "--reason",
            "Clean signature",
            "--project-path",
            str(tmp_path),
        ],
    )
    assert res_dec.exit_code == 0
    assert "Recorded human decision" in res_dec.output

    # Verify decision event recorded in DB
    evts = store.get_events(tree_id)
    assert any(e.kind == EventKind.HUMAN_DECISION_RECORDED for e in evts)

    # 3. Test promote command
    res_promo = runner.invoke(cli, ["promote", tree_id, "--project-path", str(tmp_path)])
    assert res_promo.exit_code == 0
    assert "Successfully Promoted" in res_promo.output

    # Verify target file updated in workspace
    greet_file = tmp_path / "greet.py"
    assert greet_file.exists()
    assert "def greet(): return 'hello world'" in greet_file.read_text(encoding="utf-8")


def test_sst_promote_rejects_unverified_candidate(tmp_path: Path) -> None:
    db_dir = tmp_path / ".sst"
    db_dir.mkdir(parents=True, exist_ok=True)
    tree_id = "tree_unverified"
    store = SQLiteSSTStore(db_dir / f"{tree_id}.db")

    events = [
        SSTEvent(
            event_id="e1",
            tree_id=tree_id,
            kind=EventKind.TREE_CREATED,
            idempotency_key="k1",
            payload={"tree_id": tree_id, "root_goal": "Broken candidate"},
        ),
        SSTEvent(
            event_id="e2",
            tree_id=tree_id,
            node_id="cand_fail",
            kind=EventKind.NODE_PROPOSED,
            idempotency_key="k2",
            payload={"role": "DIVERGE", "title": "Fail", "target_paths": ["fail.py"], "patch_diff": "syntax error"},
        ),
        SSTEvent(
            event_id="e3",
            tree_id=tree_id,
            node_id="cand_fail",
            kind=EventKind.VERIFIER_FINISHED,
            idempotency_key="k3",
            payload={"passed": False, "exit_code": 1, "failure_reason": "Syntax error"},
        ),
        SSTEvent(
            event_id="e4",
            tree_id=tree_id,
            node_id="cand_fail",
            kind=EventKind.PROMOTION_RECOMMENDED,
            idempotency_key="k4",
            payload={"champion_node_id": "cand_fail"},
        ),
    ]

    for e in events:
        store.append_event(e)

    runner = CliRunner()
    res = runner.invoke(cli, ["promote", tree_id, "--candidate-id", "cand_fail", "--project-path", str(tmp_path)])
    assert res.exit_code != 0
    assert "verifier did not pass" in res.output


def test_sst_promote_rejects_base_commit_mismatch(tmp_path: Path) -> None:
    db_dir = tmp_path / ".sst"
    db_dir.mkdir(parents=True, exist_ok=True)
    tree_id = "tree_commit_mismatch"
    store = SQLiteSSTStore(db_dir / f"{tree_id}.db")

    events = [
        SSTEvent(
            event_id="e1",
            tree_id=tree_id,
            kind=EventKind.TREE_CREATED,
            idempotency_key="k1",
            payload={"tree_id": tree_id, "root_goal": "Commit mismatch test", "base_commit": "old_commit_12345678"},
        ),
        SSTEvent(
            event_id="e2",
            tree_id=tree_id,
            node_id="cand_1",
            kind=EventKind.NODE_PROPOSED,
            idempotency_key="k2",
            payload={"title": "Proposal", "target_paths": ["test.py"], "patch_diff": "print('ok')\n"},
        ),
        SSTEvent(
            event_id="e3",
            tree_id=tree_id,
            node_id="cand_1",
            kind=EventKind.VERIFIER_FINISHED,
            idempotency_key="k3",
            payload={
                "passed": True,
                "patch_hash": "793a210873171ec132b5126dd0daabfc1827572ead1f1f3525ece2df8d81e92c",
                "exit_code": 0,
            },
        ),
        SSTEvent(
            event_id="e4",
            tree_id=tree_id,
            node_id="cand_1",
            kind=EventKind.PROMOTION_RECOMMENDED,
            idempotency_key="k4",
            payload={"champion_node_id": "cand_1"},
        ),
    ]

    for e in events:
        store.append_event(e)

    # In a git directory when git commit does not match old_commit_12345678, promotion must fail closed
    subprocess.run(["git", "init"], cwd=str(tmp_path), capture_output=True, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=str(tmp_path), capture_output=True, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"], cwd=str(tmp_path), capture_output=True, check=True
    )
    (tmp_path / "init.txt").write_text("init")
    subprocess.run(["git", "add", "."], cwd=str(tmp_path), capture_output=True, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=str(tmp_path), capture_output=True, check=True)

    runner = CliRunner()
    res = runner.invoke(cli, ["promote", tree_id, "--project-path", str(tmp_path)])
    assert res.exit_code != 0
    assert "Base commit mismatch" in res.output


def test_sst_promote_direct_candidate_id(tmp_path: Path) -> None:
    db_dir = tmp_path / ".sst"
    db_dir.mkdir(parents=True, exist_ok=True)
    tree_id = "tree_direct_cand"
    store = SQLiteSSTStore(db_dir / f"{tree_id}.db")

    events = [
        SSTEvent(
            event_id="e1",
            tree_id=tree_id,
            kind=EventKind.TREE_CREATED,
            idempotency_key="k1",
            payload={"tree_id": tree_id, "root_goal": "Direct candidate promote", "base_commit": "non_git_workspace"},
        ),
        SSTEvent(
            event_id="e2",
            tree_id=tree_id,
            node_id="cand_target_xyz",
            kind=EventKind.NODE_PROPOSED,
            idempotency_key="k2",
            payload={"title": "Proposal XYZ", "target_paths": ["direct.py"], "patch_diff": "def direct(): return 42\n"},
        ),
        SSTEvent(
            event_id="e3",
            tree_id=tree_id,
            node_id="cand_target_xyz",
            kind=EventKind.VERIFIER_FINISHED,
            idempotency_key="k3",
            payload={
                "passed": True,
                "patch_hash": "357d5bfd26a0e5756f0f2a32d716b8cb9794e4905fe9c18c1e582479202ad496",
                "exit_code": 0,
            },
        ),
        SSTEvent(
            event_id="e4",
            tree_id=tree_id,
            node_id="cand_target_xyz",
            kind=EventKind.PROMOTION_RECOMMENDED,
            idempotency_key="k4",
            payload={"champion_node_id": "cand_target_xyz"},
        ),
    ]
    for e in events:
        store.append_event(e)

    runner = CliRunner()
    # Promote by candidate ID directly without specifying tree_id
    res = runner.invoke(cli, ["promote", "cand_target_xyz", "--project-path", str(tmp_path)])
    assert res.exit_code == 0
    assert "Successfully Promoted" in res.output
    assert (tmp_path / "direct.py").exists()
    assert "def direct(): return 42" in (tmp_path / "direct.py").read_text(encoding="utf-8")


def test_sst_promote_rejects_human_rejected_candidate(tmp_path: Path) -> None:
    db_dir = tmp_path / ".sst"
    db_dir.mkdir(parents=True, exist_ok=True)
    tree_id = "tree_human_rej"
    store = SQLiteSSTStore(db_dir / f"{tree_id}.db")

    events = [
        SSTEvent(
            event_id="e1",
            tree_id=tree_id,
            kind=EventKind.TREE_CREATED,
            idempotency_key="k1",
            payload={"tree_id": tree_id, "root_goal": "Goal", "base_commit": "non_git_workspace"},
        ),
        SSTEvent(
            event_id="e2",
            tree_id=tree_id,
            node_id="cand_rejected",
            kind=EventKind.NODE_PROPOSED,
            idempotency_key="k2",
            payload={"title": "Proposal", "target_paths": ["rej.py"], "patch_diff": "x = 1\n"},
        ),
        SSTEvent(
            event_id="e3",
            tree_id=tree_id,
            node_id="cand_rejected",
            kind=EventKind.VERIFIER_FINISHED,
            idempotency_key="k3",
            payload={
                "passed": True,
                "patch_hash": "c6d41e5b30632e9db335ea549ed2846ccd39dc0012e51282fca2715d508ca0e5",
                "exit_code": 0,
            },
        ),
        SSTEvent(
            event_id="e4",
            tree_id=tree_id,
            node_id="cand_rejected",
            kind=EventKind.HUMAN_DECISION_RECORDED,
            idempotency_key="k4",
            payload={"verdict": "REJECTED", "reason": "Security concern"},
        ),
    ]
    for e in events:
        store.append_event(e)

    runner = CliRunner()
    res = runner.invoke(cli, ["promote", tree_id, "--candidate-id", "cand_rejected", "--project-path", str(tmp_path)])
    assert res.exit_code != 0
    assert "rejected by human" in res.output


def test_sst_promote_rejects_scope_violation(tmp_path: Path) -> None:
    db_dir = tmp_path / ".sst"
    db_dir.mkdir(parents=True, exist_ok=True)
    tree_id = "tree_scope_viol"
    store = SQLiteSSTStore(db_dir / f"{tree_id}.db")

    events = [
        SSTEvent(
            event_id="e1",
            tree_id=tree_id,
            kind=EventKind.TREE_CREATED,
            idempotency_key="k1",
            payload={
                "tree_id": tree_id,
                "root_goal": "Scope test",
                "base_commit": "non_git_workspace",
                "allowed_paths": ["src/safe.py"],
                "forbidden_paths": ["secrets/key.txt"],
            },
        ),
        SSTEvent(
            event_id="e2",
            tree_id=tree_id,
            node_id="cand_scope_viol",
            kind=EventKind.NODE_PROPOSED,
            idempotency_key="k2",
            payload={
                "title": "Violating Proposal",
                "target_paths": ["secrets/key.txt"],
                "patch_diff": "secret = 123\n",
            },
        ),
        SSTEvent(
            event_id="e3",
            tree_id=tree_id,
            node_id="cand_scope_viol",
            kind=EventKind.VERIFIER_FINISHED,
            idempotency_key="k3",
            payload={
                "passed": True,
                "patch_hash": "c5e2226d29d99c287c26f7ef89748e34f17efa59b1476d8ff8ec267600e5308e",
                "exit_code": 0,
            },
        ),
    ]
    for e in events:
        store.append_event(e)

    runner = CliRunner()
    res = runner.invoke(cli, ["promote", tree_id, "--candidate-id", "cand_scope_viol", "--project-path", str(tmp_path)])
    assert res.exit_code != 0
    assert "Scope Policy Violation" in res.output


def test_sst_promote_requires_human_decision_approval(tmp_path: Path) -> None:
    db_dir = tmp_path / ".sst"
    db_dir.mkdir(parents=True, exist_ok=True)
    tree_id = "tree_human_req"
    store = SQLiteSSTStore(db_dir / f"{tree_id}.db")

    events = [
        SSTEvent(
            event_id="e1",
            tree_id=tree_id,
            kind=EventKind.TREE_CREATED,
            idempotency_key="k1",
            payload={"tree_id": tree_id, "root_goal": "Goal requiring review", "base_commit": "non_git_workspace"},
        ),
        SSTEvent(
            event_id="e2",
            tree_id=tree_id,
            node_id="cand_review_needed",
            kind=EventKind.NODE_PROPOSED,
            idempotency_key="k2",
            payload={"title": "Proposal With Deletion", "target_paths": ["app.py"], "patch_diff": "x = 42\n"},
        ),
        SSTEvent(
            event_id="e3",
            tree_id=tree_id,
            node_id="cand_review_needed",
            kind=EventKind.VERIFIER_FINISHED,
            idempotency_key="k3",
            payload={
                "passed": True,
                "patch_hash": "60bb89a1eb6563aa778dfc1af520995d83774a74acebc7468ee866ad44ced759",
                "exit_code": 0,
            },
        ),
        SSTEvent(
            event_id="e4",
            tree_id=tree_id,
            node_id="cand_review_needed",
            kind=EventKind.HUMAN_DECISION_REQUESTED,
            idempotency_key="k4",
            payload={"reason": "Destructive deletion detected", "verdict": "ESCALATE_HUMAN"},
        ),
        SSTEvent(
            event_id="e5",
            tree_id=tree_id,
            node_id="cand_review_needed",
            kind=EventKind.PROMOTION_RECOMMENDED,
            idempotency_key="k5",
            payload={"champion_node_id": "cand_review_needed"},
        ),
    ]
    for e in events:
        store.append_event(e)

    runner = CliRunner()

    # 1. Attempt promote before human decision -> must fail closed
    res_fail = runner.invoke(cli, ["promote", tree_id, "--project-path", str(tmp_path)])
    assert res_fail.exit_code != 0
    assert "human decision was requested but has not been approved" in res_fail.output

    # 2. Record human approval
    res_dec = runner.invoke(
        cli,
        [
            "decide",
            tree_id,
            "cand_review_needed",
            "--verdict",
            "APPROVED",
            "--reason",
            "Reviewed & safe",
            "--project-path",
            str(tmp_path),
        ],
    )
    assert res_dec.exit_code == 0

    # 3. Promote now succeeds
    res_ok = runner.invoke(cli, ["promote", tree_id, "--project-path", str(tmp_path)])
    assert res_ok.exit_code == 0
    assert "Successfully Promoted" in res_ok.output


def test_sst_cli_visualize_export(tmp_path: Path) -> None:
    db_dir = tmp_path / ".sst"
    db_dir.mkdir(parents=True, exist_ok=True)
    tree_id = "tree_vis_test"
    store = SQLiteSSTStore(db_dir / f"{tree_id}.db")

    events = [
        SSTEvent(
            event_id="e1",
            tree_id=tree_id,
            kind=EventKind.TREE_CREATED,
            idempotency_key="k1",
            payload={
                "tree_id": tree_id,
                "root_goal": "Visualize tree",
                "base_commit": "non_git_workspace",
                "root_node_id": f"root_{tree_id}",
            },
        ),
        SSTEvent(
            event_id="e2",
            tree_id=tree_id,
            node_id="cand_v1",
            kind=EventKind.NODE_PROPOSED,
            idempotency_key="k2",
            payload={"role": "DIVERGE", "title": "Candidate 1", "target_paths": ["v.py"], "patch_diff": "x = 1"},
        ),
    ]
    for e in events:
        store.append_event(e)

    runner = CliRunner()
    html_out = tmp_path / "tree.html"
    res = runner.invoke(cli, ["visualize", tree_id, "--export-html", str(html_out), "--project-path", str(tmp_path)])
    assert res.exit_code == 0
    assert "Exported standalone SST visualization" in res.output
    assert html_out.exists()
    assert "AuDHD State Space Tree Visualizer" in html_out.read_text(encoding="utf-8")


def test_sst_promote_synthesized_candidate(tmp_path: Path) -> None:
    """Verifies that synthesized champion candidates (SYNTHESIS_PROPOSED) can be promoted."""
    db_dir = tmp_path / ".sst"
    db_dir.mkdir(parents=True, exist_ok=True)
    tree_id = "tree_synth_promo"
    store = SQLiteSSTStore(db_dir / f"{tree_id}.db")

    events = [
        SSTEvent(
            event_id="e1",
            tree_id=tree_id,
            kind=EventKind.TREE_CREATED,
            idempotency_key="k1",
            payload={
                "tree_id": tree_id,
                "root_goal": "Synthesized math function",
                "base_commit": "non_git_workspace",
                "root_node_id": f"root_{tree_id}",
            },
        ),
        SSTEvent(
            event_id="e2",
            tree_id=tree_id,
            node_id="cand_synth_01",
            kind=EventKind.SYNTHESIS_PROPOSED,
            idempotency_key="k2",
            payload={
                "parent_ids": ["cand_a", "cand_b"],
                "title": "Unified Dialectic Multiplier",
                "rationale": "Merged speed and safety",
                "target_paths": ["calc.py"],
                "patch_diff": "def mul(a: int, b: int) -> int: return a * b\n",
            },
        ),
        SSTEvent(
            event_id="e3",
            tree_id=tree_id,
            node_id="cand_synth_01",
            kind=EventKind.VERIFIER_FINISHED,
            idempotency_key="k3",
            payload={
                "passed": True,
                "patch_hash": "7cbe649983e6cc1c2e7ad622a4727de3eef8d5862ca5d63ca7b86bf80c8a3063",
                "exit_code": 0,
                "duration_seconds": 0.2,
            },
        ),
        SSTEvent(
            event_id="e4",
            tree_id=tree_id,
            node_id="cand_synth_01",
            kind=EventKind.SCORE_RECORDED,
            idempotency_key="k4",
            payload={"value_score": 0.99, "verdict": "APPROVE"},
        ),
        SSTEvent(
            event_id="e5",
            tree_id=tree_id,
            node_id="cand_synth_01",
            kind=EventKind.PROMOTION_RECOMMENDED,
            idempotency_key="k5",
            payload={"champion_node_id": "cand_synth_01"},
        ),
    ]
    for e in events:
        store.append_event(e)

    runner = CliRunner()
    res = runner.invoke(cli, ["promote", tree_id, "--project-path", str(tmp_path)])
    assert res.exit_code == 0
    assert "Candidate Successfully Promoted to Workspace" in res.output
    target_file = tmp_path / "calc.py"
    assert target_file.exists()
    assert "def mul" in target_file.read_text(encoding="utf-8")
