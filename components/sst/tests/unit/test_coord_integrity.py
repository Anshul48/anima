"""Coordinator integrity regressions (verifier defects D1, D3).

Promote must refuse logged bytes altered after verification, and `decide`
must refuse unknown node ids.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import sys
from pathlib import Path

from click.testing import CliRunner

from sst.cli.main import cli
from sst.context.capsule import ContextCapsuleCompiler
from sst.core.contracts import TaskPacket
from sst.gateway.contracts import (
    GatewayRequest,
    GatewayResponse,
    ModelCatalog,
    ModelCatalogEntry,
    ProviderKind,
    ProviderProfile,
)
from sst.gateway.gateway import ModelGateway
from sst.sandbox.custody import CandidateCustodyManager, compute_workspace_digest
from sst.search.controller import SSTSearchController
from sst.search.policy import SearchPolicy
from sst.storage.store import SQLiteSSTStore

GOOD = "VALUE = 41\n"


class _StubGateway(ModelGateway):
    def __init__(self) -> None:
        super().__init__()
        self.register_profile(
            ProviderProfile(
                name="stub",
                kind=ProviderKind.TEST,
                api_base="stub://",
                selected_model="stub-1",
                catalog=ModelCatalog(models=[ModelCatalogEntry(id="stub-1", display_label="Stub")]),
            )
        )
        for role in ("diverge", "refine", "critique", "synthesize"):
            self.set_route(role, "stub", "stub-1")

    def invoke(self, request: GatewayRequest) -> GatewayResponse:
        if request.role == "diverge":
            content = json.dumps({"branches": [{"strategy_title": "good", "proposed_changes": GOOD}]})
        elif request.role == "critique":
            content = '{"value_score": 0.9, "verdict": "APPROVE", "rationale": "stub"}'
        else:
            content = GOOD
        return GatewayResponse(
            content=content,
            profile="stub",
            model="stub-1",
            prompt_tokens=1,
            completion_tokens=1,
            total_tokens=2,
        )


def _run_search(project: Path, tree_id: str, *, real_snapshot: bool = False) -> str:
    (project / "vals.py").write_text("VALUE = 0\n", encoding="utf-8")
    (project / "check.py").write_text("from vals import VALUE\nassert VALUE == 41\n", encoding="utf-8")
    task = TaskPacket(
        task_id=f"task_{tree_id}",
        goal="Set VALUE to 41",
        source_repo_root=str(project),
        base_commit="non_git_workspace",
        snapshot_hash=compute_workspace_digest(project) if real_snapshot else "snap",
        allowed_paths=["vals.py"],
        acceptance_commands=[f'"{sys.executable}" check.py'],
    )
    db_path = project / ".sst" / f"{tree_id}.db"
    controller = SSTSearchController(
        task=task,
        gateway=_StubGateway(),
        store=SQLiteSSTStore(db_path),
        custody_manager=CandidateCustodyManager(base_worktree_dir=project / ".sst" / "worktrees"),
        policy=SearchPolicy(max_iterations=1, branching_factor=1, max_depth=2),
        capsule_compiler=ContextCapsuleCompiler(workspace_root=project),
    )
    result = asyncio.run(controller.run_search(tree_id))
    assert result.champion is not None
    return result.champion.candidate_id


def test_promote_accepts_bound_candidate(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    project.mkdir()
    cand_id = _run_search(project, "tree_bound")
    runner = CliRunner()
    res = runner.invoke(cli, ["promote", "tree_bound", "--project-path", str(project)])
    assert res.exit_code == 0, res.output
    assert (project / "vals.py").read_text(encoding="utf-8").strip() == GOOD.strip()
    assert cand_id in res.output


def test_promote_refuses_tampered_log(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    project.mkdir()
    _run_search(project, "tree_tamper")
    db_path = project / ".sst" / "tree_tamper.db"
    with sqlite3.connect(db_path) as conn:
        row = conn.execute("SELECT payload_json FROM sst_events WHERE kind = 'NODE_PROPOSED'").fetchone()
        assert row is not None
        payload = json.loads(row[0])
        payload["patch_diff"] = "VALUE = 666  # never verified\n"
        conn.execute(
            "UPDATE sst_events SET payload_json = ? WHERE kind = 'NODE_PROPOSED'",
            (json.dumps(payload),),
        )
    runner = CliRunner()
    res = runner.invoke(cli, ["promote", "tree_tamper", "--project-path", str(project)])
    assert res.exit_code == 1, res.output
    assert "differ" in res.output
    assert (project / "vals.py").read_text(encoding="utf-8") == "VALUE = 0\n"


def test_promote_accepts_undrifted_workspace(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    project.mkdir()
    _run_search(project, "tree_fresh", real_snapshot=True)
    runner = CliRunner()
    res = runner.invoke(cli, ["promote", "tree_fresh", "--project-path", str(project)])
    assert res.exit_code == 0, res.output


def test_promote_refuses_drifted_workspace(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    project.mkdir()
    _run_search(project, "tree_drift", real_snapshot=True)
    (project / "vals.py").write_text("VALUE = 999  # drift after search\n", encoding="utf-8")
    runner = CliRunner()
    res = runner.invoke(cli, ["promote", "tree_drift", "--project-path", str(project)])
    assert res.exit_code == 1, res.output
    assert "drifted" in res.output


def test_decide_rejects_ghost_node(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    project.mkdir()
    _run_search(project, "tree_ghost")
    runner = CliRunner()
    res = runner.invoke(
        cli,
        [
            "decide",
            "tree_ghost",
            "cand_ghost",
            "--verdict",
            "APPROVED",
            "--reason",
            "ghost",
            "--project-path",
            str(project),
        ],
    )
    assert res.exit_code == 1, res.output
    assert "not found" in res.output


def test_decide_accepts_known_node(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    project.mkdir()
    cand_id = _run_search(project, "tree_known")
    runner = CliRunner()
    res = runner.invoke(
        cli,
        [
            "decide",
            "tree_known",
            cand_id,
            "--verdict",
            "APPROVED",
            "--reason",
            "looks right",
            "--project-path",
            str(project),
        ],
    )
    assert res.exit_code == 0, res.output
