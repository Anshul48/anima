"""Decision endpoints driven through the exact CLI command implementations."""

from __future__ import annotations

from typing import Any

from click.testing import CliRunner

from sst.cli.main import cli as sst_cli


def run_decide_command(
    tree_id: str, node_id: str, verdict: str, reason: str, approver: str, project_path: str
) -> dict[str, Any]:
    """Invokes `sst decide` in-process so UI decisions share the CLI gates verbatim."""
    runner = CliRunner()
    result = runner.invoke(
        sst_cli,
        [
            "decide",
            tree_id,
            node_id,
            "--verdict",
            verdict,
            "--reason",
            reason,
            "--approver",
            approver,
            "--project-path",
            project_path,
        ],
        catch_exceptions=True,
    )
    return {
        "ok": result.exit_code == 0,
        "exit_code": result.exit_code,
        "output": result.output,
        "exception": "" if result.exception is None or result.exit_code == 0 else str(result.exception),
    }


def run_promote_command(tree_id: str, candidate_id: str | None, project_path: str) -> dict[str, Any]:
    """Invokes `sst promote` in-process so UI promotion shares the CLI gates verbatim."""
    args = ["promote", tree_id, "--project-path", project_path]
    if candidate_id:
        args += ["--candidate-id", candidate_id]
    runner = CliRunner()
    result = runner.invoke(sst_cli, args, catch_exceptions=True)
    return {
        "ok": result.exit_code == 0,
        "exit_code": result.exit_code,
        "output": result.output,
        "exception": "" if result.exception is None or result.exit_code == 0 else str(result.exception),
    }
