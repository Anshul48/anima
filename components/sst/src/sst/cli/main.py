"""CLI commands for State Space Tree candidate search, human decisions, and promotion."""

from __future__ import annotations

import asyncio
import os
import re
import subprocess
import time
import uuid
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from sst.cli.memory import build_memory_provider, format_provider_report
from sst.context.capsule import ContextCapsuleCompiler
from sst.core.contracts import (
    CandidateProposal,
    HumanDecisionRecord,
    SearchResult,
    TaskPacket,
    TerminationReason,
)
from sst.core.events import EventKind, SSTEvent
from sst.gateway.contracts import ModelCatalog, ModelCatalogEntry, ProviderKind, ProviderProfile
from sst.gateway.gateway import ModelGateway
from sst.sandbox.custody import (
    CandidateCustodyManager,
    compute_proposal_hash,
    compute_workspace_digest,
)
from sst.search.controller import SSTSearchController
from sst.search.policy import SearchPolicy
from sst.storage.store import SQLiteSSTStore
from sst.visualizer.server import export_html_visualization, start_visualizer_server


def _get_git_commit(project_path: Path) -> str:
    """Returns current git commit hash if in a git repository, else empty string."""
    try:
        res = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(project_path),
            capture_output=True,
            text=True,
            timeout=5,
        )
        if res.returncode == 0:
            return res.stdout.strip()
    except Exception:
        pass
    return ""


def _resolve_project(project_path: Path | str) -> Path:
    return Path(project_path).resolve()


def _resolve_db_path(project: Path, tree_id: str) -> Path:
    """Locates an existing SST tree database or returns default location."""
    candidate_locations = [
        project / ".sst" / f"{tree_id}.db",
        project / ".auto" / "sst" / f"{tree_id}.db",
        project / f"{tree_id}.db",
    ]
    for loc in candidate_locations:
        if loc.exists():
            return loc
    # Default to .sst if directory exists or .auto/sst if it exists
    if (project / ".auto" / "sst").exists():
        return project / ".auto" / "sst" / f"{tree_id}.db"
    return project / ".sst" / f"{tree_id}.db"


def _format_gateway_report(gateway: ModelGateway) -> str:
    """One-line report of wired provider profiles so TEST/fixture use is visible."""
    parts: list[str] = []
    for name, profile in gateway.profiles.items():
        roles = sorted(role for role, target in gateway.routes.items() if target.profile == name)
        role_txt = ",".join(roles) if roles else "*"
        parts.append(f"{name}:{profile.kind.name}/{profile.selected_model or '?'}[{role_txt}]")
    return "Gateway profiles: " + ("; ".join(parts) if parts else "none")


def _get_default_gateway() -> ModelGateway:
    """Builds the default gateway from environment credentials.

    Precedence: OPENAI_API_KEY (OpenAI) > DEEPSEEK_API_KEY (DeepSeek) > TEST
    fixture. OPENAI_BASE_URL/SST_MODEL override the selected base/model.
    """
    gateway = ModelGateway()
    if os.environ.get("OPENAI_API_KEY"):
        kind = ProviderKind.OPENAI_COMPATIBLE
        api_base = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
        model = os.environ.get("SST_MODEL", "gpt-4o")
    elif os.environ.get("DEEPSEEK_API_KEY"):
        kind = ProviderKind.OPENAI_COMPATIBLE
        api_base = os.environ.get("OPENAI_BASE_URL", "https://api.deepseek.com")
        model = os.environ.get("SST_MODEL", "deepseek-chat")
    else:
        kind = ProviderKind.TEST
        api_base = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
        model = os.environ.get("SST_MODEL", "gpt-4o")
    prof = ProviderProfile(
        name="default",
        kind=kind,
        api_base=api_base,
        selected_model=model,
        catalog=ModelCatalog(models=[ModelCatalogEntry(id="default-model", display_label="Default")]),
    )
    gateway.register_profile(prof)
    return gateway


@click.group("sst")
def cli() -> None:
    """Run and manage State Space Tree (SST) candidate search, human decisions, and promotion."""
    pass


# Backward compatibility alias
sst_group = cli

# Documented `sst run` exit codes (machine-caller contract).
EXIT_CHAMPION = 0  # a verified champion candidate was found
EXIT_NO_CANDIDATE = 2  # search finished with no verified candidate
EXIT_BUDGET_EXHAUSTED = 3  # search stopped on budget exhaustion without a champion
EXIT_PROVIDER_ERROR = 4  # no champion and at least one provider failure was recorded
EXIT_CANCELLED = 130  # search was cancelled before a champion was found


def exit_code_for_result(result: SearchResult) -> int:
    """Maps a SearchResult to the documented `sst run` exit code.

    A present champion always maps to 0, even when the run also stopped on
    budget exhaustion (mid-run champions are preserved by design); otherwise
    the termination reason decides, with provider failure breaking the
    no-candidate tie.
    """
    if result.champion is not None:
        return EXIT_CHAMPION
    if result.termination_reason is TerminationReason.CANCELLED:
        return EXIT_CANCELLED
    if result.termination_reason is TerminationReason.BUDGET_EXHAUSTED:
        return EXIT_BUDGET_EXHAUSTED
    if result.provider_errors:
        return EXIT_PROVIDER_ERROR
    return EXIT_NO_CANDIDATE


@cli.command("run")
@click.option("--goal", required=True, help="Engineering goal or feature specification.")
@click.option("--project-path", type=click.Path(exists=True, path_type=Path), default=".")
@click.option("--max-iterations", type=int, default=5, help="Maximum search iterations.")
@click.option(
    "--response-max-tokens",
    type=int,
    default=None,
    help="Per-request completion cap override for all roles (reasoning models need headroom above the 2048/1024 defaults).",
)
@click.option("--test-command", help="Acceptance test command to verify candidates.")
@click.option(
    "--memory-provider",
    default="none",
    help="Memory provider spec: 'none' (default) or 'static' with --memory-insight values.",
)
@click.option(
    "--memory-insight",
    multiple=True,
    help="Prior-insight string served by the 'static' memory provider (repeatable).",
)
@click.option(
    "--json",
    "json_output",
    is_flag=True,
    default=False,
    help="Print the SearchResult envelope as JSON to stdout (machine caller path).",
)
def sst_run_cmd(
    goal: str,
    project_path: Path,
    max_iterations: int,
    response_max_tokens: int | None,
    test_command: str | None,
    memory_provider: str,
    memory_insight: tuple[str, ...],
    json_output: bool,
) -> None:
    """Execute bounded State Space Tree MCTS search to find verified code solutions.

    Exit codes: 0 champion found; 2 no verified candidate; 3 budget
    exhausted; 4 provider unavailable or errored (no champion); 130 cancelled.
    """
    console = Console()
    project = _resolve_project(project_path)
    gateway = _get_default_gateway()
    provider = build_memory_provider(memory_provider, insights=list(memory_insight))
    provider_line = format_provider_report(provider)
    gateway_line = _format_gateway_report(gateway)
    if json_output:
        click.echo(provider_line, err=True)
        click.echo(gateway_line, err=True)
    else:
        console.print(f"[dim]{provider_line}[/dim]")
        console.print(f"[dim]{gateway_line}[/dim]")

    tree_id = f"tree_{uuid.uuid4().hex[:8]}"
    db_path = _resolve_db_path(project, tree_id)
    store = SQLiteSSTStore(db_path)
    custody_dir = (
        project / ".sst" / "worktrees" if (project / ".sst").exists() else project / ".auto" / "worktrees" / "sst"
    )
    custody = CandidateCustodyManager(base_worktree_dir=custody_dir)

    base_commit = _get_git_commit(project) or "non_git_workspace"
    snapshot_hash = compute_workspace_digest(project)

    task = TaskPacket(
        task_id=f"task_{tree_id}",
        goal=goal,
        source_repo_root=str(project),
        base_commit=base_commit,
        snapshot_hash=snapshot_hash,
        acceptance_commands=[test_command] if test_command else [],
    )

    policy = SearchPolicy(max_iterations=max_iterations, response_max_tokens=response_max_tokens)
    capsule_compiler = ContextCapsuleCompiler(workspace_root=project, memory_provider=provider)
    controller = SSTSearchController(
        task=task,
        gateway=gateway,
        store=store,
        custody_manager=custody,
        policy=policy,
        capsule_compiler=capsule_compiler,
    )

    if not json_output:
        console.print(
            Panel.fit(
                f"[bold green]Starting SST Candidate Search[/bold green]\nTree ID: {tree_id}\nBase Commit: {base_commit[:8]}\nGoal: {goal}"
            )
        )

    result = asyncio.run(controller.run_search(tree_id))
    champion = result.champion

    if json_output:
        # Machine caller path: the envelope JSON is the only stdout content.
        click.echo(result.model_dump_json(indent=2))
        code = exit_code_for_result(result)
        if code != EXIT_CHAMPION:
            raise SystemExit(code)
        return

    champion_verdict = "UNKNOWN"
    if champion:
        for alt in result.alternatives:
            if alt.candidate.candidate_id == champion.candidate_id and alt.score:
                champion_verdict = alt.score.critic_verdict or "UNKNOWN"
                break

    if champion:
        console.print(
            Panel.fit(
                f"[bold green]✓ Champion Candidate Discovered![/bold green]\n\n"
                f"Candidate ID: [cyan]{champion.candidate_id}[/cyan]\n"
                f"Title: {champion.title}\n"
                f"Semantic review: {champion_verdict}\n"
                f"Target Files: {champion.target_paths}\n\n"
                f"Run [bold yellow]`sst promote {tree_id} --candidate-id {champion.candidate_id}`[/bold yellow] to apply changes to workspace.",
                title="SST Search Completed",
                border_style="green",
            )
        )
    else:
        console.print("[yellow]No verified champion candidate reached promotion threshold.[/yellow]")
        console.print(f"[dim]Termination: {result.termination_reason.value}[/dim]")

    code = exit_code_for_result(result)
    if code != EXIT_CHAMPION:
        raise SystemExit(code)


@cli.command("status")
@click.argument("tree_id")
@click.option("--project-path", type=click.Path(exists=True, path_type=Path), default=".")
def sst_status_cmd(tree_id: str, project_path: Path) -> None:
    """Inspect State Space Tree events, node states, and promotion status."""
    console = Console()
    project = _resolve_project(project_path)
    db_path = _resolve_db_path(project, tree_id)

    if not db_path.exists():
        raise click.ClickException(f"No SST database found for tree '{tree_id}' at {db_path}")

    store = SQLiteSSTStore(db_path)
    rebuilt_tree = store.rebuild_tree_from_events(tree_id)

    if not rebuilt_tree:
        raise click.ClickException(f"Could not reconstruct tree '{tree_id}' from event log.")

    table = Table(title=f"SST Tree: {tree_id}", border_style="cyan")
    table.add_column("Node ID", style="cyan bold")
    table.add_column("Role", style="magenta")
    table.add_column("Status", style="green")
    table.add_column("Value Score", justify="right")
    table.add_column("Title", style="white")

    for node_id, node in rebuilt_tree.nodes.items():
        v_score = f"{node.cortex_evaluation.value_score:.2f}" if node.cortex_evaluation else "-"
        table.add_row(node_id, node.role.value, node.status.value, v_score, node.title[:40])

    console.print(table)


@cli.command("promote")
@click.argument("target_id")
@click.option("--candidate-id", help="Candidate node ID to promote. Defaults to recommended champion.")
@click.option("--project-path", type=click.Path(exists=True, path_type=Path), default=".")
def sst_promote_cmd(target_id: str, candidate_id: str | None, project_path: Path) -> None:
    """Promote an exact verified SST candidate proposal directly into the active workspace.

    Accepts either a TREE_ID or CANDIDATE_ID as the primary argument.
    """
    console = Console()
    project = _resolve_project(project_path)

    tree_id = target_id
    explicit_cand_id = candidate_id

    # 1. Resolve tree_id and candidate_id from target_id argument
    db_path = _resolve_db_path(project, tree_id)
    if not db_path.exists():
        # Search all possible database directories for this target_id
        found_tree_id: str | None = None
        for search_dir in [project / ".sst", project / ".auto" / "sst", project]:
            if search_dir.exists():
                for p in search_dir.glob("*.db"):
                    t_store = SQLiteSSTStore(p)
                    evts = t_store.get_events(p.stem)
                    if any(e.node_id == target_id or e.payload.get("champion_node_id") == target_id for e in evts):
                        found_tree_id = p.stem
                        db_path = p
                        break
            if found_tree_id:
                break
        if found_tree_id:
            tree_id = found_tree_id
            explicit_cand_id = target_id

    if not db_path.exists():
        raise click.ClickException(f"No SST database found for tree or candidate '{target_id}' at {db_path}")

    store = SQLiteSSTStore(db_path)
    events = store.get_events(tree_id)

    # 2. Check Base Commit Freshness
    tree_init_evt = next((e for e in events if e.kind == EventKind.TREE_CREATED), None)
    task: TaskPacket | None = None
    if tree_init_evt:
        expected_base = str(tree_init_evt.payload.get("base_commit", ""))
        current_head = _get_git_commit(project)
        if current_head and expected_base and expected_base != "non_git_workspace" and current_head != expected_base:
            raise click.ClickException(
                f"Base commit mismatch: Candidate was generated against base '{expected_base[:8]}', "
                f"but current checkout is at '{current_head[:8]}'. Re-verify search against current HEAD before promoting."
            )
        task = TaskPacket(
            task_id=str(tree_init_evt.payload.get("task_id", f"task_{tree_id}")),
            goal=str(tree_init_evt.payload.get("root_goal", "")),
            source_repo_root=str(project),
            base_commit=expected_base or "non_git_workspace",
            snapshot_hash=str(tree_init_evt.payload.get("snapshot_hash", "")),
            allowed_paths=list(tree_init_evt.payload.get("allowed_paths", [])),
            forbidden_paths=list(tree_init_evt.payload.get("forbidden_paths", [])),
        )
        logged_snapshot = str(tree_init_evt.payload.get("snapshot_hash", ""))
        if re.fullmatch(r"[0-9a-f]{64}", logged_snapshot):
            if compute_workspace_digest(project) != logged_snapshot:
                raise click.ClickException(
                    f"Workspace drifted since search for tree '{tree_id}' "
                    "(snapshot mismatch: files changed after verification). Re-run search."
                )
        elif logged_snapshot:
            click.echo(
                "Warning: snapshot_hash is not a workspace digest; staleness not enforced.",
                err=True,
            )

    target_cand_id = explicit_cand_id
    if not target_cand_id:
        # Find PROMOTION_RECOMMENDED event
        for e in reversed(events):
            if e.kind == EventKind.PROMOTION_RECOMMENDED:
                target_cand_id = e.payload.get("champion_node_id")
                break

    if not target_cand_id:
        raise click.ClickException("No champion candidate found. Specify `--candidate-id` explicitly.")

    # 3. Find proposed candidate event
    cand_event: SSTEvent | None = None
    for e in events:
        if (
            e.kind in {EventKind.NODE_PROPOSED, EventKind.CANDIDATE_CREATED, EventKind.SYNTHESIS_PROPOSED}
            and e.node_id == target_cand_id
        ):
            cand_event = e
            break

    if not cand_event:
        raise click.ClickException(f"Candidate '{target_cand_id}' not found in event history.")

    # 4. Check that candidate satisfies human decision requirements
    human_decision_requested = any(
        e.kind == EventKind.HUMAN_DECISION_REQUESTED and e.node_id == target_cand_id for e in events
    )
    if human_decision_requested:
        approved = any(
            e.kind == EventKind.HUMAN_DECISION_RECORDED
            and e.node_id == target_cand_id
            and e.payload.get("verdict") == "APPROVED"
            for e in events
        )
        if not approved:
            raise click.ClickException(
                f"Cannot promote candidate '{target_cand_id}': human decision was requested but has not been approved."
            )
    else:
        for e in events:
            if e.kind == EventKind.HUMAN_DECISION_RECORDED and e.node_id == target_cand_id:
                if e.payload.get("verdict") == "REJECTED":
                    raise click.ClickException(
                        f"Cannot promote candidate '{target_cand_id}': candidate was explicitly rejected by human decision."
                    )

    # 5. Verify that candidate passed deterministic verifier, bound to exact bytes.
    verifier_evt: SSTEvent | None = None
    for e in events:
        if e.kind == EventKind.VERIFIER_FINISHED and e.node_id == target_cand_id:
            if e.payload.get("passed") is True:
                verifier_evt = e
                break

    if verifier_evt is None:
        raise click.ClickException(f"Cannot promote candidate '{target_cand_id}': verifier did not pass.")

    logged_hash = str(verifier_evt.payload.get("patch_hash", ""))
    if not logged_hash:
        raise click.ClickException(
            f"Cannot promote candidate '{target_cand_id}': verifier record has no integrity binding "
            "(pre-binding log or tampered record). Re-run search to produce a bound record."
        )
    raw_ops = cand_event.payload.get("file_operations", [])
    logged_ops = [dict(op) for op in raw_ops] if isinstance(raw_ops, list) else []
    current_hash = compute_proposal_hash(str(cand_event.payload.get("patch_diff", "")), logged_ops)
    if current_hash != logged_hash:
        raise click.ClickException(
            f"Cannot promote candidate '{target_cand_id}': logged bytes differ from verified bytes "
            "(record altered after verification). Re-run search."
        )

    # 6. Apply exact patch to project workspace with scope and containment checks
    custody_dir = (
        project / ".sst" / "worktrees" if (project / ".sst").exists() else project / ".auto" / "worktrees" / "sst"
    )
    custody = CandidateCustodyManager(base_worktree_dir=custody_dir)
    proposal = CandidateProposal(
        candidate_id=target_cand_id,
        tree_id=tree_id,
        title=str(cand_event.payload.get("title", "")),
        rationale="Promoted champion",
        target_paths=list(cand_event.payload.get("target_paths", [])),
        patch_diff=str(cand_event.payload.get("patch_diff", "")),
        file_operations=list(cand_event.payload.get("file_operations", [])),
    )

    app_res = custody.apply_proposal(proposal, project, task=task)
    if not app_res.success:
        raise click.ClickException(f"Promotion failed during patch apply: {app_res.error_message}")

    # 7. Record PROMOTION_RECORDED event
    store.append_event(
        SSTEvent(
            event_id=f"evt_{uuid.uuid4().hex[:12]}",
            tree_id=tree_id,
            node_id=target_cand_id,
            kind=EventKind.PROMOTION_RECORDED,
            idempotency_key=f"promoted_{tree_id}_{target_cand_id}",
            payload={"champion_node_id": target_cand_id, "applied_files": app_res.applied_files},
        )
    )

    console.print(
        Panel.fit(
            f"[bold green]✓ Candidate Successfully Promoted to Workspace![/bold green]\n\n"
            f"Tree: {tree_id}\n"
            f"Candidate: {target_cand_id}\n"
            f"Files Updated: {app_res.applied_files}",
            border_style="green",
        )
    )


@cli.command("decide")
@click.argument("tree_id")
@click.argument("node_id")
@click.option("--verdict", type=click.Choice(["APPROVED", "REJECTED", "REVISED"]), required=True)
@click.option("--reason", required=True, help="Reasoning or architectural justification.")
@click.option("--approver", default="operator", help="Human operator identifier.")
@click.option("--project-path", type=click.Path(exists=True, path_type=Path), default=".")
def sst_decide_cmd(tree_id: str, node_id: str, verdict: str, reason: str, approver: str, project_path: Path) -> None:
    """Record an explicit human decision on an SST candidate branch."""
    console = Console()
    project = _resolve_project(project_path)
    db_path = _resolve_db_path(project, tree_id)

    if not db_path.exists():
        raise click.ClickException(f"No SST database found for tree '{tree_id}'")

    decision_id = f"dec_{uuid.uuid4().hex[:12]}"
    record = HumanDecisionRecord(
        decision_id=decision_id,
        tree_id=tree_id,
        node_id=node_id,
        reason=reason,
        verdict=verdict,
        approver=approver,
    )
    decision_hash = record.compute_hash()

    store = SQLiteSSTStore(db_path)
    known_nodes = {e.node_id for e in store.get_events(tree_id) if e.node_id}
    if node_id not in known_nodes:
        raise click.ClickException(f"Cannot record decision: node '{node_id}' not found in tree '{tree_id}'.")
    store.append_event(
        SSTEvent(
            event_id=f"evt_{uuid.uuid4().hex[:12]}",
            tree_id=tree_id,
            node_id=node_id,
            kind=EventKind.HUMAN_DECISION_RECORDED,
            actor=approver,
            idempotency_key=f"decision_{tree_id}_{node_id}_{verdict}",
            payload={
                "decision_id": decision_id,
                "decision_hash": decision_hash,
                "verdict": verdict,
                "reason": reason,
                "approver": approver,
                "node_id": node_id,
            },
        )
    )

    console.print(
        f"[green]Recorded human decision '{verdict}' on node '{node_id}' (hash: {decision_hash[:12]}).[/green]"
    )


@cli.command("visualize")
@click.argument("tree_id")
@click.option("--port", type=int, default=8501, help="Port to serve interactive Cytoscape.js DAG visualizer.")
@click.option("--host", default="127.0.0.1", help="Host interface to bind server.")
@click.option("--export-html", type=click.Path(path_type=Path), help="Export static HTML visualization to file.")
@click.option("--project-path", type=click.Path(exists=True, path_type=Path), default=".")
def sst_visualize_cmd(tree_id: str, port: int, host: str, export_html: Path | None, project_path: Path) -> None:
    """Launch live Cytoscape.js SST DAG Visualizer with SSE streaming or export static HTML."""
    console = Console()
    project = _resolve_project(project_path)
    db_path = _resolve_db_path(project, tree_id)

    if not db_path.exists():
        raise click.ClickException(f"No SST database found for tree '{tree_id}' at {db_path}")

    store = SQLiteSSTStore(db_path)
    rebuilt_tree = store.rebuild_tree_from_events(tree_id)

    if not rebuilt_tree:
        raise click.ClickException(f"Could not reconstruct tree '{tree_id}' from event log.")

    if export_html:
        export_html_visualization(rebuilt_tree, export_html)
        console.print(f"[bold green]✓ Exported standalone SST visualization to {export_html}[/bold green]")
        return

    server = start_visualizer_server(
        tree_data=lambda: store.rebuild_tree_from_events(tree_id) or rebuilt_tree,
        port=port,
        host=host,
        store=store,
        tree_id=tree_id,
    )
    console.print(
        Panel.fit(
            f"[bold green]🌲 SST Visualizer Running[/bold green]\n\n"
            f"URL: [bold cyan]http://{host}:{port}[/bold cyan]\n"
            f"Tree ID: {tree_id}\n\n"
            f"Open the URL in your browser to inspect live DAG branching, node diffs, and critic evaluations.\n"
            f"Press [bold yellow]Ctrl+C[/bold yellow] to stop server.",
            title="State Space Tree Visualizer",
            border_style="cyan",
        )
    )
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        console.print("\n[yellow]Stopping visualizer server...[/yellow]")
        server.shutdown()
        server.server_close()


@cli.command("ui")
@click.option("--port", type=int, default=8501, help="Port to serve the SST task UI (loopback only).")
@click.option("--project-path", type=click.Path(path_type=Path), default=".")
def sst_ui_cmd(port: int, project_path: Path) -> None:
    """Launch the SST task-to-result web UI: tasks, runs, alternatives, decisions, promotion."""
    from sst.ui.app import create_server

    console = Console()
    project = _resolve_project(project_path)
    server = create_server(project, port)
    console.print(
        Panel.fit(
            f"[bold green]SST Task UI Running[/bold green]\n\n"
            f"URL: [bold cyan]http://127.0.0.1:{port}[/bold cyan]\n"
            f"Project: {project}\n\n"
            f"Open the URL in your browser to create tasks, run searches, compare "
            f"alternatives, record decisions, and promote candidates.\n"
            f"Press [bold yellow]Ctrl+C[/bold yellow] to stop server.",
            title="State Space Tree",
            border_style="green",
        )
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        console.print("\n[yellow]Stopping SST UI server...[/yellow]")
    finally:
        server.shutdown()
        server.server_close()
