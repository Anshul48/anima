"""Full-featured Typer CLI for Entorhinal Contextual Intelligence System.

Commands:
- entorhinal status: Daemon health, active projection version, journal stats.
- entorhinal inspect [timeline|graph|focus]: Real-time context, timeline, and entity graphs.
- entorhinal correct <fact_id> <new_value>: Submits permanent user correction lock.
- entorhinal forget --start <time> --end <time>: Cryptographic cascade deletion.
- entorhinal grants [list|grant|revoke]: Dynamic consent management.
- entorhinal audit: Inspect consumer query and policy audit logs.
- entorhinal serve: Start local loopback FastAPI daemon.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
from typing import Optional
import uuid

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.tree import Tree
import typer
import uvicorn

from entorhinal.evidence.journal import EvidenceJournal
from entorhinal.policy.engine import PolicyEngine
from entorhinal.projections.compiler import MultiTimescaleCompiler
from entorhinal.projections.models import EntityNodeType, ImmediateFocusState
from entorhinal.schemas.models import CorrectionAction, SourceType
from entorhinal.user_control.service import UserControlService

# Initialize Typer App & Rich Console
app = typer.Typer(name="entorhinal", help="Entorhinal: Local-First Contextual Intelligence System", no_args_is_help=True)
inspect_app = typer.Typer(name="inspect", help="Inspect real-time context, entity graphs, and timelines", no_args_is_help=True)
grants_app = typer.Typer(name="grants", help="Manage source and domain capture permissions", no_args_is_help=True)
sources_app = typer.Typer(name="sources", help="Inspect and control source adapters (per-source stop/start)", no_args_is_help=True)
auth_app = typer.Typer(name="auth", help="Bootstrap and manage HTTP principal credentials", no_args_is_help=True)
activity_app = typer.Typer(name="activity", help="Inspect local activity sessions and explanations", no_args_is_help=True)

app.add_typer(inspect_app, name="inspect")
app.add_typer(grants_app, name="grants")
app.add_typer(sources_app, name="sources")
app.add_typer(auth_app, name="auth")
app.add_typer(activity_app, name="activity")

console = Console()
logger = logging.getLogger(__name__)


def get_default_services(storage_dir: Optional[str] = None):
    """Instantiate legacy local services (vNext/init paths only).

    All durable-runtime commands (status, inspect, correct, forget, grants,
    audit, sources, retention) use :func:`open_cli_runtime` instead so the
    CLI operates the same SQLite store/policy/controls as ``serve`` (F3).
    """
    base_dir = Path(storage_dir) if storage_dir else Path.home() / ".entorhinal"
    base_dir.mkdir(parents=True, exist_ok=True)
    journal_path = base_dir / "evidence_journal.jsonl"

    journal = EvidenceJournal(storage_path=journal_path)
    policy = PolicyEngine()
    compiler = MultiTimescaleCompiler(journal=journal)
    user_control = UserControlService(
        journal=journal,
        policy_engine=policy,
        compiler=compiler,
        storage_dir=base_dir,
    )
    return journal, policy, compiler, user_control


def open_cli_runtime(storage_dir: Optional[str] = None):
    """Build the durable runtime for one-shot CLI commands (F3).

    Same ``build_runtime`` path as ``serve`` on the same ``--dir`` root, so
    reads, corrections, grants, and deletions observe the daemon's SQLite
    store, persisted consent rules, and control metadata. Callers must
    ``close()`` the returned runtime (it opens the store directly; no daemon
    needs to be running).
    """
    from entorhinal.runtime.config import RuntimeConfig
    from entorhinal.runtime.factory import build_runtime

    root = Path(storage_dir) if storage_dir else Path.home() / ".entorhinal"
    return build_runtime(RuntimeConfig.from_root(root))


# ==============================================================================
# Command: init & setup (Interactive Onboarding Wizard)
# ==============================================================================

@app.command("init")
def init_cmd(
    storage_dir: Optional[str] = typer.Option(None, "--dir", "-d", help="Storage directory path (default: ~/.entorhinal)"),
    quick: bool = typer.Option(False, "--quick", "-q", help="Quick non-interactive setup using system defaults"),
    local_only: bool = typer.Option(False, "--local-only", help="Configure Option A: 100% Local-Only air-gapped models"),
    cloud_only: bool = typer.Option(False, "--cloud-only", help="Configure Option B: Cloud-Only LiteLLM models"),
    hybrid: bool = typer.Option(False, "--hybrid", help="Configure Option C: Hybrid Local + Cloud models (Default)"),
) -> None:
    """Launch interactive onboarding wizard (Hermes/OpenClaw-grade setup for Windows 11)."""
    from entorhinal.cli.init_wizard import InteractiveSetupWizard
    wizard = InteractiveSetupWizard(target_dir=storage_dir)

    preset_mode = None
    if local_only:
        preset_mode = "local"
    elif cloud_only:
        preset_mode = "cloud"
    elif hybrid:
        preset_mode = "hybrid"

    if quick:
        mode = preset_mode or "hybrid"
        cfg = wizard.run_non_interactive(storage_dir=storage_dir, mode=mode)
        console.print(f"[bold green]Quick initialization complete![/bold green] Config saved to {cfg.storage_dir}/config.yaml")
    else:
        wizard.run_interactive(preset_mode=preset_mode)


@app.command("setup")
def setup_cmd(
    storage_dir: Optional[str] = typer.Option(None, "--dir", "-d", help="Storage directory path (default: ~/.entorhinal)"),
    quick: bool = typer.Option(False, "--quick", "-q", help="Quick non-interactive setup using system defaults"),
    local_only: bool = typer.Option(False, "--local-only", help="Configure Option A: 100% Local-Only air-gapped models"),
    cloud_only: bool = typer.Option(False, "--cloud-only", help="Configure Option B: Cloud-Only LiteLLM models"),
    hybrid: bool = typer.Option(False, "--hybrid", help="Configure Option C: Hybrid Local + Cloud models (Default)"),
) -> None:
    """Alias for 'entorhinal init'."""
    init_cmd(storage_dir=storage_dir, quick=quick, local_only=local_only, cloud_only=cloud_only, hybrid=hybrid)


# ==============================================================================
# Command: status
# ==============================================================================

@app.command("status")
def status_cmd(
    storage_dir: Optional[str] = typer.Option(None, "--dir", "-d", help="Runtime storage root (same --dir as 'entorhinal serve')"),
) -> None:
    """Show measured store/control health, projection version, and record stats."""
    runtime = open_cli_runtime(storage_dir)
    try:
        store = runtime.store
        user_control = runtime.user_control
        record_count = asyncio.run(store.count_records())
        is_valid, corrupted_id, _corrupted_idx = store.verify_journal_integrity()
        last_hash = asyncio.run(store.get_last_hash())
        corrections_count = len(user_control.list_corrections())
        grants_count = len(user_control.list_consent_rules())
        health = runtime.health()
    finally:
        runtime.close()

    from entorhinal.ai.config import EntorhinalConfig
    cfg = EntorhinalConfig.load_from_dir(storage_dir)

    # Measured health (F13): every component of the verdict is observed from
    # the runtime just opened — no literal HEALTHY/VERIFIED strings.
    store_health = health["store"]
    writer_alive = bool(store_health.get("writer_alive"))
    journal_ok = str(store_health.get("journal_mode", "")).upper() == "DELETE"
    sync_ok = store_health.get("synchronous") == 3  # EXTRA
    pending = int(store_health.get("pending_work", 0))
    sources_health = health["sources"]
    configured = list(sources_health.get("configured_sources", []))
    verdict_ok = bool(is_valid and writer_alive and journal_ok and sync_ok)
    if verdict_ok:
        daemon_status = (
            "[bold green]HEALTHY[/bold green] "
            f"(measured: integrity=valid writer=alive journal=DELETE sync=EXTRA "
            f"records={record_count} pending={pending})"
        )
    else:
        daemon_status = (
            "[bold red]DEGRADED[/bold red] "
            f"(measured: integrity={'valid' if is_valid else 'BROKEN:' + str(corrupted_id)} "
            f"writer={'alive' if writer_alive else 'DEAD'} "
            f"journal={store_health.get('journal_mode')} sync={store_health.get('synchronous')} "
            f"pending={pending})"
        )

    table = Table(title="Entorhinal System Status", border_style="cyan", show_header=True, header_style="bold magenta")
    table.add_column("Component", style="bold white", width=24)
    table.add_column("Value", style="green")

    table.add_row("Daemon Status", daemon_status)
    table.add_row("Backend", f"sqlite ({store_health.get('db_path')})")
    table.add_row("Loopback Address", f"{cfg.daemon.host}:{cfg.daemon.port}")
    table.add_row("Named Pipe IPC", cfg.daemon.named_pipe_path)
    table.add_row("AI Mode", f"[bold cyan]{cfg.ai.mode.upper()}[/bold cyan] ({'ENABLED' if cfg.ai.enabled else 'DISABLED'})")
    table.add_row("Primary Model", cfg.ai.primary_model)
    table.add_row("Fallback Model", cfg.ai.fallback_model or "None")
    table.add_row("Embedding Model", cfg.ai.embedding_model)
    table.add_row("Projection Version", runtime.compiler.graph_manager.version)
    table.add_row("Total Evidence Records", str(record_count))
    table.add_row("Cryptographic Integrity", "[bold green]VERIFIED (hash chain continuous)[/bold green]" if is_valid else f"[bold red]CORRUPTED ({corrupted_id})[/bold red]")
    table.add_row("Latest Hash Chain", f"{last_hash[:16]}...{last_hash[-16:]}")
    table.add_row("Active User Corrections", str(corrections_count))
    table.add_row("Active Consent Grants", str(grants_count))
    table.add_row("Configured Sources", ", ".join(configured) if configured else "(none configured)")
    table.add_row("Pump", "not started (one-shot CLI; running daemon owns the pump)")
    table.add_row("Action Authority", "[bold yellow]ZERO (Advisory Only)[/bold yellow]")

    console.print(table)


# ==============================================================================
# Inspect Subcommands: timeline, graph, focus
# ==============================================================================

@inspect_app.command("timeline")
def inspect_timeline_cmd(
    limit: int = typer.Option(20, "--limit", "-n", help="Number of records to show"),
    storage_dir: Optional[str] = typer.Option(None, "--dir", "-d", help="Data directory path"),
) -> None:
    """Display real-time chronological evidence timeline and session clusters."""
    runtime = open_cli_runtime(storage_dir)
    try:
        records = asyncio.run(runtime.store.scan_evidence(limit=limit))
    finally:
        runtime.close()

    if not records:
        console.print(Panel("No evidence records found in journal.", title="Timeline", border_style="yellow"))
        return

    table = Table(title=f"Evidence Timeline (Recent {len(records)} Events)", border_style="blue", show_header=True, header_style="bold cyan")
    table.add_column("Timestamp (UTC)", style="white", width=20)
    table.add_column("Source", style="bold yellow", width=12)
    table.add_column("App Identifier", style="bold green", width=18)
    table.add_column("Title / Target URI", style="dim white")
    table.add_column("Classification", style="magenta", width=12)
    table.add_column("Tombstone", style="red", width=10)

    for r in records:
        table.add_row(
            r.persisted_at.strftime("%Y-%m-%d %H:%M:%S"),
            r.source_type.value,
            r.app_identifier,
            (r.window_title or r.target_uri or "")[:60],
            r.classification.value,
            "YES" if r.is_tombstone else "NO",
        )

    console.print(table)


@inspect_app.command("graph")
def inspect_graph_cmd(
    node_type: Optional[str] = typer.Option(None, "--type", "-t", help="Filter by entity node type (project, tool, goal, topic)"),
    storage_dir: Optional[str] = typer.Option(None, "--dir", "-d", help="Data directory path"),
) -> None:
    """Display entity nodes and relation graph using rich hierarchy formatting."""
    runtime = open_cli_runtime(storage_dir)
    try:
        compiler = runtime.compiler
        asyncio.run(compiler.compile_batch_projection())
        nodes = compiler.graph_manager.list_nodes()
    finally:
        runtime.close()
    if node_type:
        nodes = [n for n in nodes if n.entity_type.value.lower() == node_type.lower()]

    if not nodes:
        console.print(Panel("No semantic graph nodes found.", title="Entity Graph", border_style="yellow"))
        return

    root_tree = Tree("[bold cyan]Entorhinal Semantic Entity Graph[/bold cyan]")
    by_type: dict[str, list] = {}
    for n in nodes:
        t_val = n.entity_type.value if isinstance(n.entity_type, EntityNodeType) else str(n.entity_type)
        by_type.setdefault(t_val, []).append(n)

    for t_val, t_nodes in by_type.items():
        type_branch = root_tree.add(f"[bold magenta]{t_val.upper()}[/bold magenta] ({len(t_nodes)} nodes)")
        for n in t_nodes:
            node_leaf = type_branch.add(f"[bold green]{n.name}[/bold green] ([dim]{n.entity_uri}[/dim]) - conf: {n.confidence:.2f}")
            if n.attributes:
                for k, v in n.attributes.items():
                    node_leaf.add(f"[dim]{k}:[/dim] {str(v)[:40]}")

    console.print(root_tree)


@inspect_app.command("focus")
def inspect_focus_cmd(
    storage_dir: Optional[str] = typer.Option(None, "--dir", "-d", help="Data directory path"),
) -> None:
    """Display the real-time immediate focus state."""
    runtime = open_cli_runtime(storage_dir)
    try:
        context = runtime.compiler.get_current_context()
    finally:
        runtime.close()
    focus = context.immediate_focus

    if isinstance(focus, ImmediateFocusState):
        app_id = focus.app_identifier
        win_title = focus.window_title or "N/A"
        uri = focus.target_uri or "N/A"
        dwell = f"{focus.duration_seconds:.1f}s"
        ts = focus.timestamp.strftime("%Y-%m-%d %H:%M:%S UTC")
    elif isinstance(focus, dict) and focus:
        app_id = focus.get("app_identifier", "idle")
        win_title = focus.get("window_title", "N/A")
        uri = focus.get("target_uri", "N/A")
        dwell = f"{focus.get('duration_seconds', 0.0):.1f}s"
        ts = str(focus.get("timestamp", ""))
    else:
        app_id = "system.idle"
        win_title = "Idle"
        uri = "N/A"
        dwell = "0.0s"
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    content = f"""[bold white]App Identifier:[/bold white] [green]{app_id}[/green]
[bold white]Window Title:[/bold white]   {win_title}
[bold white]Target URI:[/bold white]     [blue]{uri}[/blue]
[bold white]Dwell Duration:[/bold white] {dwell}
[bold white]Timestamp:[/bold white]      {ts}"""

    console.print(Panel(content, title="[bold cyan]Real-Time Immediate Focus[/bold cyan]", border_style="green"))


# ==============================================================================
# Command: correct
# ==============================================================================

@app.command("correct")
def correct_cmd(
    fact_id: str = typer.Argument(..., help="Target DerivedFact ID or Entity URI to override"),
    new_value: str = typer.Argument(..., help="Corrected value (JSON string or raw text)"),
    note: Optional[str] = typer.Option(None, "--note", "-m", help="User explanation / note"),
    action: str = typer.Option("overwrite", "--action", "-a", help="Correction action: overwrite, exclude, delete"),
    storage_dir: Optional[str] = typer.Option(None, "--dir", "-d", help="Data directory path"),
) -> None:
    """Submit permanent user correction override lock for a fact or entity."""
    runtime = open_cli_runtime(storage_dir)
    try:
        user_control = runtime.user_control
        try:
            val: object = json.loads(new_value)
        except Exception:
            val = new_value

        act = CorrectionAction(action.lower())
        corr = asyncio.run(user_control.submit_user_correction(
            target_entity_or_fact_id=fact_id,
            corrected_value=val,
            user_note=note,
            override_action=act,
        ))
    finally:
        runtime.close()

    panel = Panel(
        f"[bold green]Correction Applied Successfully![/bold green]\n"
        f"[bold white]Correction ID:[/bold white] {corr.correction_id}\n"
        f"[bold white]Target ID:[/bold white]     {corr.target_entity_or_fact_id}\n"
        f"[bold white]Action:[/bold white]        {corr.override_action.value}\n"
        f"[bold white]Value:[/bold white]         {corr.corrected_value}\n"
        f"[bold white]User Note:[/bold white]     {corr.user_comment or 'None'}\n"
        f"[bold yellow]Status: PERMANENT_OVERRIDE RECORDED (id {corr.correction_id})[/bold yellow]",
        title="User Sovereignty Lock",
        border_style="green",
    )
    console.print(panel)


# ==============================================================================
# Command: forget
# ==============================================================================

def _parse_forget_source_specs(source: list[str], source_opt: list[str]) -> list:
    """Parse serve-compatible --source/--source-opt flags for the residue scan."""
    from entorhinal.runtime.config import SourceSpec

    specs: list = []
    for item in source:
        key, _, name = item.partition(":")
        key = key.strip()
        name = name.strip() or key
        if not key:
            console.print("[bold red]Invalid --source value (empty registry key).[/bold red]")
            raise typer.Exit(code=1)
        specs.append(SourceSpec(name=name, adapter=key))

    options_by_name: dict[str, dict] = {}
    for opt in source_opt:
        name_key, sep, value = opt.partition("=")
        if not sep or not name_key.strip():
            console.print(f"[bold red]Invalid --source-opt value {opt!r}; expected '<name>.<key>=<value>'.[/bold red]")
            raise typer.Exit(code=1)
        match = ""
        for spec in specs:
            prefix = spec.name + "."
            if name_key.startswith(prefix) and len(spec.name) > len(match):
                match = spec.name
        if not match:
            console.print(f"[bold red]--source-opt for unconfigured source in {opt!r}; "
                          f"configured: {sorted(s.name for s in specs) or 'none'}.[/bold red]")
            raise typer.Exit(code=1)
        key = name_key[len(match) + 1:]
        if not key.strip():
            console.print(f"[bold red]Invalid --source-opt value {opt!r}; expected '<name>.<key>=<value>'.[/bold red]")
            raise typer.Exit(code=1)
        options_by_name.setdefault(match, {})[key.strip()] = value
    if options_by_name:
        remapped: list = []
        for spec in specs:
            extra = options_by_name.get(spec.name, {})
            remapped.append(SourceSpec(
                name=spec.name, adapter=spec.adapter,
                enabled=spec.enabled, options={**spec.options, **extra},
            ))
        specs = remapped
    return specs


@app.command("forget")
def forget_cmd(
    start: str = typer.Option(..., "--start", "-s", help="Start timestamp (ISO format, e.g. 2026-08-17T00:00:00Z)"),
    end: str = typer.Option(..., "--end", "-e", help="End timestamp (ISO format, e.g. 2026-08-17T23:59:59Z)"),
    reason: str = typer.Option("User CLI deletion command", "--reason", "-r", help="Reason for revocation"),
    storage_dir: Optional[str] = typer.Option(None, "--dir", "-d", help="Runtime storage root (same --dir as 'entorhinal serve')"),
    source: Optional[list[str]] = typer.Option(None, "--source", help="Source adapter '<registry-key>[:<name>]' for the residue scan (repeatable)"),
    source_opt: Optional[list[str]] = typer.Option(None, "--source-opt", help="Adapter option '<name>.<key>=<value>' for the residue scan (repeatable)"),
) -> None:
    """Execute cryptographic cascade deletion ("Forget Time Range") on the durable runtime."""
    from entorhinal.runtime.config import RuntimeConfig
    from entorhinal.runtime.factory import build_runtime

    try:
        st = datetime.fromisoformat(start.replace("Z", "+00:00"))
        et = datetime.fromisoformat(end.replace("Z", "+00:00"))
    except Exception as e:
        console.print(f"[bold red]Invalid timestamp format:[/bold red] {e}")
        raise typer.Exit(code=1)

    # F3: forget operates on the durable SQLite runtime the daemon serves,
    # never on the legacy JSONL journal. No daemon needs to be running;
    # the store is opened directly and closed after the proof is computed.
    root = Path(storage_dir) if storage_dir else Path.home() / ".entorhinal"
    config = RuntimeConfig.from_root(root)
    if not config.db_path.exists():
        console.print(f"[bold red]No durable runtime at {root} (missing {config.db_filename}).[/bold red]")
        console.print("Run forget against the same --dir as 'entorhinal serve'.")
        raise typer.Exit(code=1)
    specs = _parse_forget_source_specs(list(source or []), list(source_opt or []))
    if specs:
        config = RuntimeConfig.from_root(root, sources=specs)
    runtime = build_runtime(config)
    try:
        proof = asyncio.run(runtime.user_control.forget_time_range(
            start_time=st,
            end_time=et,
            reason=reason,
        ))
    finally:
        runtime.close()

    uncovered = proof.get("uncovered_residues", [])
    spool_purged = sum(r.get("purged_lines", 0) for r in proof.get("producer_residues", []))

    table = Table(title="Cryptographic Deletion Verification Proof", border_style="red", show_header=True, header_style="bold red")
    table.add_column("Metric", style="bold white", width=28)
    table.add_column("Result", style="green")

    table.add_row("Deletion Run ID", proof["deletion_id"])
    table.add_row("Backend", str(proof.get("backend", "?")))
    table.add_row("Deletion Generation", str(proof.get("deletion_generation", "?")))
    table.add_row("Tombstoned Store Records", str(proof["tombstoned_records_count"]))
    table.add_row("Purged Graph Nodes", str(proof["purged_nodes_count"]))
    table.add_row("Journal Chain Integrity", "[bold green]VERIFIED[/bold green]" if proof["journal_integrity_valid"] else "[bold red]FAIL[/bold red]")
    leaks = proof["residual_leakage_count"]
    table.add_row("Residual Payload Leakage", f"[bold green]{leaks} records[/bold green]" if leaks == 0 else f"[bold red]{leaks} records[/bold red]")
    table.add_row("Spool Lines Purged", str(spool_purged))
    if uncovered:
        table.add_row("Uncovered Residues", f"[bold yellow]{len(uncovered)} file(s) retain copies (see proof)[/bold yellow]")
    else:
        table.add_row("Uncovered Residues", "[bold green]none[/bold green]")
    if leaks == 0 and proof["journal_integrity_valid"]:
        table.add_row("Status", "[bold green]COMPLETE & ERASED (store); see residues for producer scope[/bold green]")
    else:
        table.add_row("Status", "[bold red]COMPLETE WITH RESIDUALS - INVESTIGATE[/bold red]")

    console.print(table)


# ==============================================================================
# Grants Subcommands: list, grant, revoke
# ==============================================================================

@grants_app.command("list")
def grants_list_cmd(
    storage_dir: Optional[str] = typer.Option(None, "--dir", "-d", help="Data directory path"),
) -> None:
    """List active source and domain consent rules."""
    runtime = open_cli_runtime(storage_dir)
    try:
        rules = runtime.user_control.list_consent_rules()
    finally:
        runtime.close()

    if not rules:
        console.print(Panel("No explicit consent rules configured (default deny; nothing is admitted without a grant).", title="Grants", border_style="yellow"))
        return

    table = Table(title="Consent & Governance Rules", border_style="green", show_header=True, header_style="bold green")
    table.add_column("Rule ID", style="bold white", width=36)
    table.add_column("Permission", style="bold", width=10)
    table.add_column("Source Type", style="cyan", width=14)
    table.add_column("App Pattern", style="yellow")
    table.add_column("Domain Pattern", style="magenta")
    table.add_column("Priority", style="white", width=8)

    for r in rules:
        perm_str = "[bold green]ALLOW[/bold green]" if r.allow else "[bold red]DENY[/bold red]"
        table.add_row(
            r.rule_id,
            perm_str,
            r.source_type.value if r.source_type else "*",
            r.app_pattern or "*",
            r.domain_pattern or "*",
            str(r.priority),
        )

    console.print(table)


@grants_app.command("grant")
def grants_grant_cmd(
    source: str = typer.Option("browser", "--source", "-s", help="Source type (browser, os_window, terminal_pty)"),
    app_pat: str = typer.Option("*", "--app", "-a", help="Application pattern"),
    domain_pat: str = typer.Option("*", "--domain", "-m", help="Domain pattern"),
    storage_dir: Optional[str] = typer.Option(None, "--dir", "-d", help="Data directory path"),
) -> None:
    """Grant capture consent for a source, app, or domain."""
    runtime = open_cli_runtime(storage_dir)
    try:
        st = SourceType(source.lower())
        rule_id = asyncio.run(runtime.user_control.grant_consent(
            source_type=st,
            app_pattern=app_pat,
            domain_pattern=domain_pat,
        ))
    finally:
        runtime.close()
    console.print(f"[bold green]Consent granted successfully![/bold green] Rule ID: [cyan]{rule_id}[/cyan]")


@grants_app.command("revoke")
def grants_revoke_cmd(
    rule_id: str = typer.Argument(..., help="Rule ID to revoke"),
    storage_dir: Optional[str] = typer.Option(None, "--dir", "-d", help="Data directory path"),
) -> None:
    """Revoke an active consent rule by ID."""
    runtime = open_cli_runtime(storage_dir)
    try:
        revoked = asyncio.run(runtime.user_control.revoke_consent(rule_id))
    finally:
        runtime.close()
    if revoked:
        console.print(f"[bold green]Rule {rule_id} revoked successfully.[/bold green]")
    else:
        console.print(f"[bold red]Rule {rule_id} not found.[/bold red]")


# ==============================================================================
# Sources Subcommands: list, stop, start (F11)
# ==============================================================================

@sources_app.command("list")
def sources_list_cmd(
    storage_dir: Optional[str] = typer.Option(None, "--dir", "-d", help="Runtime storage root (same --dir as 'entorhinal serve')"),
) -> None:
    """List configured sources, live state, and durable stop records."""
    runtime = open_cli_runtime(storage_dir)
    try:
        health = runtime.sources.health()
        stopped = runtime.sources.stopped_sources()
    finally:
        runtime.close()

    per_source = dict(health.get("sources", {}))
    for name in stopped:
        per_source.setdefault(name, {
            "adapter": "(no serve-time spec in this one-shot view)",
            "configured": False,
            "is_running": False,
            "is_healthy": False,
            "state": "stopped",
            "stopped_reason": stopped[name].get("reason", ""),
            "stopped_at": stopped[name].get("stopped_at"),
        })

    if not per_source:
        console.print(Panel("No sources configured and no stop records.", title="Sources", border_style="yellow"))
        return

    table = Table(title="Sources", border_style="green", show_header=True, header_style="bold green")
    table.add_column("Source", style="bold white", width=24)
    table.add_column("Adapter", style="cyan", width=18)
    table.add_column("State", style="bold", width=14)
    table.add_column("Healthy", style="bold", width=8)
    table.add_column("Stop Reason", style="yellow")

    for name in sorted(per_source):
        detail = per_source[name]
        state = str(detail.get("state", "running" if detail.get("is_running") else "unknown"))
        healthy = detail.get("is_healthy", False)
        table.add_row(
            name,
            str(detail.get("adapter", "?")),
            state,
            "[bold green]YES[/bold green]" if healthy else "[bold red]NO[/bold red]",
            str(detail.get("stopped_reason", "") or "-"),
        )

    console.print(table)
    if health.get("stopped_records_error"):
        console.print(f"[bold red]Stop records unreadable: {health['stopped_records_error']}[/bold red]")


@sources_app.command("stop")
def sources_stop_cmd(
    name: str = typer.Argument(..., help="Source name to stop"),
    reason: str = typer.Option("", "--reason", "-r", help="Reason for stopping the source"),
    storage_dir: Optional[str] = typer.Option(None, "--dir", "-d", help="Runtime storage root (same --dir as 'entorhinal serve')"),
) -> None:
    """Stop one source (halt adapter, freeze cursor) without deleting history.

    Writes a durable stop record: a running daemon halts the live adapter on
    its next pump tick, and the source stays stopped across restarts until
    'sources start'. Distinct from consent revocation and from deletion.
    """
    runtime = open_cli_runtime(storage_dir)
    try:
        result = runtime.sources.record_stop(name, reason=reason)
    finally:
        runtime.close()
    console.print(f"[bold green]Source {result['name']} stop recorded[/bold green] "
                  f"(durable={result['durable']}, at={result['stopped_at']}).")
    console.print("A running daemon halts the adapter on its next pump tick; "
                  "otherwise the stop takes effect on the next daemon start.")


@sources_app.command("start")
def sources_start_cmd(
    name: str = typer.Argument(..., help="Source name to start"),
    storage_dir: Optional[str] = typer.Option(None, "--dir", "-d", help="Runtime storage root (same --dir as 'entorhinal serve')"),
) -> None:
    """Clear one source's stop record so it runs again."""
    runtime = open_cli_runtime(storage_dir)
    try:
        result = runtime.sources.clear_stop_record(name)
    finally:
        runtime.close()
    if result["stop_cleared"]:
        console.print(f"[bold green]Source {result['name']} stop cleared.[/bold green]")
        console.print("A running daemon restarts it on its next pump tick; "
                      "otherwise it starts on the next daemon start.")
    else:
        console.print(f"[yellow]Source {result['name']} had no stop record; nothing to clear.[/yellow]")


# ==============================================================================
# Auth Subcommands: bootstrap, grant, revoke, list (F1 credential seam)
# ==============================================================================

def _open_auth_store(storage_dir: Optional[str]):
    """Open the runtime-root auth store (sibling API-builder contract)."""
    from entorhinal.runtime.auth import AuthStore
    from entorhinal.runtime.config import RuntimeConfig

    root = Path(storage_dir) if storage_dir else Path.home() / ".entorhinal"
    return AuthStore(RuntimeConfig.from_root(root).auth_path)


@auth_app.command("bootstrap")
def auth_bootstrap_cmd(
    storage_dir: Optional[str] = typer.Option(None, "--dir", "-d", help="Runtime storage root (same --dir as 'entorhinal serve')"),
) -> None:
    """Create the first admin principal (only when the store is empty).

    Prints the bearer [REDACTED] ONCE; it is never stored in the clear and
    cannot be recovered. All HTTP disclosure routes return 401 until this runs.
    """
    store = _open_auth_store(storage_dir)
    created = store.ensure_bootstrap_admin()
    if created is None:
        console.print("[yellow]Auth store already has principals; no bootstrap performed.[/yellow]")
        console.print("Use 'entorhinal auth grant' to add principals or 'auth list' to inspect.")
        raise typer.Exit(code=1)
    principal, secret = created
    console.print(f"[bold green]Bootstrap admin created:[/bold green] {principal.principal_id}")
    console.print(f"[bold red]Bearer [REDACTED] (shown ONCE, save it now):[/bold red] {secret}")
    console.print("Send as 'Authorization: Bearer <secret>' on every HTTP disclosure route.")


@auth_app.command("grant")
def auth_grant_cmd(
    principal_id: str = typer.Option(..., "--id", help="Principal id to create"),
    role: str = typer.Option(..., "--role", help="Role: source, reader, or admin"),
    purpose: Optional[list[str]] = typer.Option(None, "--purpose", help="Allowed purpose (repeatable)"),
    scope: Optional[list[str]] = typer.Option(None, "--scope", help="Allowed scope (repeatable)"),
    source_id: Optional[str] = typer.Option(None, "--source-id", help="Pinned source id (source role only)"),
    max_budget: int = typer.Option(4096, "--max-budget", help="Maximum token budget for this principal"),
    label: str = typer.Option("", "--label", help="Human label for the principal"),
    storage_dir: Optional[str] = typer.Option(None, "--dir", "-d", help="Runtime storage root (same --dir as 'entorhinal serve')"),
) -> None:
    """Create a principal with explicit grants; prints its secret once."""
    store = _open_auth_store(storage_dir)
    try:
        principal, secret = store.create_principal(
            role=role,
            principal_id=principal_id,
            allowed_purposes=list(purpose or []),
            allowed_scopes=list(scope or []),
            max_budget=max_budget,
            source_id=source_id,
            label=label,
        )
    except ValueError as e:
        console.print(f"[bold red]Cannot create principal:[/bold red] {e}")
        raise typer.Exit(code=1)
    console.print(f"[bold green]Principal created:[/bold green] {principal.principal_id} (role={principal.role})")
    console.print(f"[bold red]Bearer [REDACTED] (shown ONCE, save it now):[/bold red] {secret}")


@auth_app.command("revoke")
def auth_revoke_cmd(
    principal_id: str = typer.Argument(..., help="Principal id to revoke"),
    storage_dir: Optional[str] = typer.Option(None, "--dir", "-d", help="Runtime storage root (same --dir as 'entorhinal serve')"),
) -> None:
    """Revoke a principal; its credential immediately stops authenticating."""
    store = _open_auth_store(storage_dir)
    if store.revoke(principal_id):
        console.print(f"[bold green]Principal {principal_id} revoked.[/bold green]")
    else:
        console.print(f"[bold red]Principal {principal_id} not found.[/bold red]")
        raise typer.Exit(code=1)


@auth_app.command("list")
def auth_list_cmd(
    storage_dir: Optional[str] = typer.Option(None, "--dir", "-d", help="Runtime storage root (same --dir as 'entorhinal serve')"),
) -> None:
    """List principals and their grants (secrets are never shown)."""
    store = _open_auth_store(storage_dir)
    principals = store.list_principals()
    if not principals:
        console.print(Panel("No principals. Run 'entorhinal auth bootstrap' first; until then all HTTP disclosure routes return 401.", title="Auth", border_style="yellow"))
        return
    table = Table(title="Auth Principals", border_style="green", show_header=True, header_style="bold green")
    table.add_column("Principal", style="bold white", width=24)
    table.add_column("Role", style="cyan", width=8)
    table.add_column("Purposes", style="yellow")
    table.add_column("Scopes", style="magenta")
    table.add_column("Disabled", style="bold", width=9)
    for p in principals:
        table.add_row(
            p.principal_id,
            p.role,
            ", ".join(p.allowed_purposes) or "-",
            ", ".join(p.allowed_scopes) or "-",
            "YES" if p.disabled else "no",
        )
    console.print(table)


# ==============================================================================
# Command: retention (G23)
# ==============================================================================

@app.command("retention")
def retention_cmd(
    max_age_days: int = typer.Option(30, "--max-age-days", help="Payload retention window in days (P11 default 30)"),
    max_db_bytes: int = typer.Option(1 << 30, "--max-db-bytes", help="Retained store ceiling in bytes (P11 default 1 GiB)"),
    enforce: bool = typer.Option(False, "--enforce", help="Tombstone records older than the window (explicit only)"),
    storage_dir: Optional[str] = typer.Option(None, "--dir", "-d", help="Runtime storage root (same --dir as 'entorhinal serve')"),
) -> None:
    """Show measured retention state; optionally enforce the age window."""
    runtime = open_cli_runtime(storage_dir)
    try:
        status = runtime.store.retention_status(
            max_age_days=max_age_days, max_db_bytes=max_db_bytes
        )
        proof = None
        if enforce:
            proof = asyncio.run(runtime.user_control.enforce_retention(
                max_age_days=max_age_days
            ))
    finally:
        runtime.close()

    table = Table(title="Retention Status (measured)", border_style="cyan", show_header=True, header_style="bold cyan")
    table.add_column("Metric", style="bold white", width=24)
    table.add_column("Value", style="green")
    table.add_row("Age Window (days)", str(status["max_age_days"]))
    table.add_row("Cutoff", str(status["cutoff_iso"]))
    table.add_row("Evidence Rows", str(status["evidence_count"]))
    table.add_row("Expired Rows", str(status["expired_count"]))
    table.add_row("Oldest Commit", str(status["oldest_committed_at"] or "-"))
    table.add_row("Newest Commit", str(status["newest_committed_at"] or "-"))
    table.add_row("DB Bytes", f"{status['db_bytes']} / ceiling {status['max_db_bytes']}")
    table.add_row("Over Size Ceiling", "YES" if status["over_size_ceiling"] else "no")
    console.print(table)

    if proof is not None:
        table2 = Table(title="Retention Enforcement Proof", border_style="red", show_header=True, header_style="bold red")
        table2.add_column("Metric", style="bold white", width=24)
        table2.add_column("Result", style="green")
        table2.add_row("Candidates", str(proof.get("expired_count", proof.get("tombstoned_records_count", 0))))
        table2.add_row("Tombstoned", str(proof.get("tombstoned_records_count", 0)))
        table2.add_row("Deletion Generation", str(proof.get("deletion_generation", "-")))
        table2.add_row("Residual Leakage", str(proof.get("residual_leakage_count", "-")))
        console.print(table2)


# ==============================================================================
# Activity Subcommands: sessions, explain (activity-build §8.4 inspection)
# ==============================================================================

def _open_activity_view(storage_dir: Optional[str], limit: int = 100000):
    """Build a one-shot activity view from committed store evidence.

    Uses the component's ``from_evidence_records`` loader over the durable
    SQLite store: tombstoned rows are skipped by the loader, so inspection
    reflects current control state. The runtime's persisted activity grants
    gate the view (deny-by-default, same as the daemon). Returns
    (service, record_count).
    """
    from entorhinal.activity.grants import GrantStore
    from entorhinal.activity.service import ActivityService

    runtime = open_cli_runtime(storage_dir)
    try:
        records = asyncio.run(runtime.store.scan_evidence(limit=limit))
        activity_dir = Path(runtime.config.storage_root) / "activity"
    finally:
        runtime.close()
    grants = GrantStore(activity_dir / "grants.json")
    service = ActivityService.from_evidence_records(records, grants=grants)
    return service, len(records)


@activity_app.command("sessions")
def activity_sessions_cmd(
    activity: Optional[str] = typer.Option(None, "--activity", "-a", help="Filter by classified activity (e.g. lecture-viewing, coding)"),
    limit: int = typer.Option(50, "--limit", "-n", help="Maximum sessions to show"),
    storage_dir: Optional[str] = typer.Option(None, "--dir", "-d", help="Runtime storage root (same --dir as 'entorhinal serve')"),
) -> None:
    """List logical activity sessions derived from committed evidence."""
    try:
        service, record_count = _open_activity_view(storage_dir)
    except ImportError as e:
        console.print(f"[bold red]Activity component unavailable:[/bold red] {e}")
        raise typer.Exit(code=1)
    sessions = service.list_sessions(activity=activity)[:limit]

    if not sessions:
        console.print(Panel(
            f"No logical sessions derived from {record_count} evidence record(s) "
            f"({service.load_skipped} skipped as non-activity/tombstoned).",
            title="Activity Sessions", border_style="yellow"))
        return

    labels = {l.target_id: l for l in service.labels() if l.target_kind == "session"}
    spans_by_id = {sp.span_id: sp for sp in service.spans()}
    table = Table(title=f"Activity Sessions ({len(sessions)} shown)", border_style="cyan", show_header=True, header_style="bold cyan")
    # No fixed widths: session ids must render in full (they key `explain`).
    table.add_column("Session", style="bold white", overflow="fold")
    table.add_column("Spans", style="white")
    table.add_column("Active", style="green")
    table.add_column("Elapsed", style="white")
    table.add_column("GapCaps", style="yellow")
    table.add_column("Activity", style="magenta")
    table.add_column("Conf", style="yellow")
    table.add_column("Identity", style="dim white", overflow="fold")
    for s in sessions:
        label = labels.get(s.session_id)
        identity = getattr(s.content_identity, "content_key", None) or s.identity_status
        # F2 consumer guidance: a long silent gap never splits a span, so
        # active time is step-capped while elapsed stays truthful. Surface
        # both plus the capped-step count so presence is never assumed.
        gap_caps = sum(
            spans_by_id[sid].provenance.capped_steps
            for sid in s.span_ids
            if sid in spans_by_id
        )
        table.add_row(
            s.session_id,
            str(len(s.span_ids)),
            f"{s.total_active_seconds:.0f}s",
            f"{s.total_elapsed_seconds:.0f}s",
            str(gap_caps),
            label.activity if label else "-",
            f"{label.confidence:.2f}" if label else "-",
            str(identity)[:48],
        )
    console.print(table)
    # Full ids verbatim: table cells may fold on narrow terminals, but the
    # ids that key `activity explain` must always be present contiguously.
    for s in sessions:
        console.print(f"session_id: {s.session_id}")


@activity_app.command("explain")
def activity_explain_cmd(
    session_id: str = typer.Argument(..., help="Logical session id to explain"),
    storage_dir: Optional[str] = typer.Option(None, "--dir", "-d", help="Runtime storage root (same --dir as 'entorhinal serve')"),
) -> None:
    """Explain why a session is shaped the way it is (links, labels, uncertainty)."""
    try:
        service, _ = _open_activity_view(storage_dir)
    except ImportError as e:
        console.print(f"[bold red]Activity component unavailable:[/bold red] {e}")
        raise typer.Exit(code=1)
    explanation = service.explain_session(session_id)
    if explanation is None:
        console.print(f"[bold red]Session {session_id} not found in committed evidence.[/bold red]")
        raise typer.Exit(code=1)

    console.print(Panel(explanation.summary, title=f"Session {session_id}", border_style="cyan"))
    view = service.get_session_view(session_id)
    if view is not None and view.spans:
        timing = Table(title="Span Timing", border_style="cyan", show_header=True, header_style="bold cyan")
        timing.add_column("Span", style="bold white", width=20)
        timing.add_column("Active", style="green", width=10)
        timing.add_column("Elapsed", style="white", width=10)
        timing.add_column("CappedSteps", style="yellow", width=11)
        timing.add_column("Background", style="dim white", width=10)
        for sp in view.spans:
            timing.add_row(
                sp.span_id,
                f"{sp.active_seconds:.0f}s",
                f"{sp.elapsed_seconds:.0f}s",
                str(sp.provenance.capped_steps),
                "yes" if sp.background else "no",
            )
        console.print(timing)
    if explanation.resumption_evidence:
        table = Table(title="Resumption Evidence", border_style="green", show_header=True, header_style="bold green")
        table.add_column("Evidence", style="white")
        for item in explanation.resumption_evidence:
            table.add_row(json.dumps(item, default=str)[:100])
        console.print(table)
    if explanation.why_not_linked:
        table = Table(title="Considered But Not Linked", border_style="yellow", show_header=True, header_style="bold yellow")
        table.add_column("Reason", style="white")
        for item in explanation.why_not_linked:
            table.add_row(json.dumps(item, default=str)[:100])
        console.print(table)
    if explanation.label_basis or explanation.label_uncertainty:
        basis = "\n".join(f"- {b}" for b in explanation.label_basis) or "-"
        uncertainty = "\n".join(f"- {u}" for u in explanation.label_uncertainty) or "none stated"
        console.print(Panel(f"[bold white]Label basis:[/bold white]\n{basis}\n\n"
                            f"[bold white]Uncertainty:[/bold white]\n{uncertainty}",
                            title="Classification", border_style="magenta"))


@activity_app.command("provision-grant")
def activity_provision_grant_cmd(
    source_id: str = typer.Option(..., "--source-id", help="Producer source id (e.g. entorhinal.activity.browser.01)"),
    principal_id: str = typer.Option(..., "--principal", help="Source principal id to create for this producer"),
    grant_id: Optional[str] = typer.Option(None, "--grant-id", help="Grant id (default: generated grant-<rand8>)"),
    app: Optional[list[str]] = typer.Option(None, "--app", help="Permitted app substring (repeatable; empty = any app)"),
    domain: Optional[list[str]] = typer.Option(None, "--domain", help="Permitted domain (repeatable; empty = any domain)"),
    kind: Optional[list[str]] = typer.Option(None, "--kind", help="Permitted event kind (repeatable; empty = any kind)"),
    label: str = typer.Option("", "--label", help="Human label for the principal"),
    storage_dir: Optional[str] = typer.Option(None, "--dir", "-d", help="Runtime storage root (same --dir as 'entorhinal serve')"),
) -> None:
    """Provision one producer credential + opt-in grant (activity §8.5).

    Creates a source-role principal (Bearer [REDACTED] printed ONCE) and a
    SourceGrant persisted at <root>/activity/grants.json. Paste the token
    and grant id into the producer's options page; nothing is captured
    until the user also enables the producer and grants hosts there.
    Requires 'entorhinal auth bootstrap' first.
    """
    from entorhinal.activity.events import ActivityKind
    from entorhinal.activity.grants import GrantStore, SourceGrant
    from entorhinal.runtime.config import RuntimeConfig

    store = _open_auth_store(storage_dir)
    if not store.list_principals():
        console.print("[bold red]Auth store is empty; run 'entorhinal auth bootstrap' first.[/bold red]")
        raise typer.Exit(code=1)
    kinds: list[str] = []
    for raw in kind or []:
        try:
            kinds.append(ActivityKind(raw.strip()).value)
        except ValueError:
            valid = sorted(k.value for k in ActivityKind)
            console.print(f"[bold red]Invalid --kind {raw!r}; expected one of: {', '.join(valid)}[/bold red]")
            raise typer.Exit(code=1)
    try:
        principal, secret = store.create_principal(
            role="source",
            principal_id=principal_id,
            source_id=source_id,
            label=label,
        )
    except ValueError as e:
        console.print(f"[bold red]Cannot create principal:[/bold red] {e}")
        raise typer.Exit(code=1)
    root = Path(storage_dir) if storage_dir else Path.home() / ".entorhinal"
    config = RuntimeConfig.from_root(root)
    config.ensure_root()
    grant_store = GrantStore(config.storage_root / "activity" / "grants.json")
    resolved_grant_id = (grant_id or "").strip() or f"grant-{uuid.uuid4().hex[:8]}"
    if grant_store.get(resolved_grant_id) is not None:
        console.print(f"[bold red]Grant {resolved_grant_id} already exists; principal {principal.principal_id} was created (revoke it if unwanted).[/bold red]")
        raise typer.Exit(code=1)
    grant_store.add(SourceGrant(
        grant_id=resolved_grant_id,
        source_id=source_id,
        principal=principal.principal_id,
        allow_apps=list(app or []),
        allow_domains=list(domain or []),
        allow_kinds=list(kinds),
        note=label,
    ))
    console.print(f"[bold green]Producer provisioned:[/bold green] grant_id={resolved_grant_id} principal={principal.principal_id}")
    console.print(f"[bold red]Bearer [REDACTED] (shown ONCE, save it now):[/bold red] {secret}")
    console.print(f"Grant file: {grant_store.path}")
    console.print("Next: paste the token + grant id into the producer options page, "
                  "grant hosts there, and enable the producer (default OFF).")


# ==============================================================================
# Command: audit
# ==============================================================================

@app.command("audit")
def audit_cmd(
    limit: int = typer.Option(30, "--limit", "-n", help="Number of audit records to show"),
    consumer: Optional[str] = typer.Option(None, "--consumer", "-c", help="Filter by consumer ID"),
    storage_dir: Optional[str] = typer.Option(None, "--dir", "-d", help="Data directory path"),
) -> None:
    """Inspect consumer query audit logs and policy decisions."""
    runtime = open_cli_runtime(storage_dir)
    try:
        logs = asyncio.run(runtime.user_control.get_audit_log(limit=limit, consumer_filter=consumer))
    finally:
        runtime.close()

    if not logs:
        console.print(Panel("No audit events recorded yet.", title="Audit Trail", border_style="yellow"))
        return

    table = Table(title=f"Audit Log (Recent {len(logs)} Events)", border_style="magenta", show_header=True, header_style="bold magenta")
    table.add_column("Timestamp (UTC)", style="white", width=20)
    table.add_column("Action", style="bold cyan", width=24)
    table.add_column("Consumer", style="bold yellow", width=18)
    table.add_column("Permitted", style="bold", width=10)
    table.add_column("Details", style="dim white")

    for ev in logs:
        perm_str = "[bold green]YES[/bold green]" if ev.get("permitted", True) else "[bold red]NO[/bold red]"
        details_str = json.dumps(ev.get("details", {}), default=str)[:60]
        table.add_row(
            ev.get("timestamp", "")[:19].replace("T", " "),
            ev.get("action", ""),
            str(ev.get("consumer_id", "user")),
            perm_str,
            details_str,
        )

    console.print(table)


# ==============================================================================
# Command: serve
# ==============================================================================

@app.command("serve")
def serve_cmd(
    host: str = typer.Option("127.0.0.1", "--host", "-h", help="Loopback host to bind daemon"),
    port: int = typer.Option(8000, "--port", "-p", help="Port to listen on"),
    reload: bool = typer.Option(False, "--reload", help="Enable auto-reload for development"),
    wire_sources: bool = typer.Option(False, "--wire-sources", "-w", help="Start the configured source adapters with the live admission pipeline"),
    storage_dir: Optional[str] = typer.Option(None, "--dir", "-d", help="Runtime storage root (default: ~/.entorhinal)"),
    source: Optional[list[str]] = typer.Option(None, "--source", "-s", help="Source adapter '<registry-key>[:<name>]' (repeatable)"),
    source_opt: Optional[list[str]] = typer.Option(None, "--source-opt", help="Adapter option '<name>.<key>=<value>' (repeatable)"),
) -> None:
    """Start the local loopback FastAPI daemon on the durable runtime."""
    if host not in ("127.0.0.1", "localhost", "::1"):
        console.print("[bold red]Security Error: Entorhinal daemon binds exclusively to local loopback (127.0.0.1).[/bold red]")
        raise typer.Exit(code=1)

    from entorhinal.api.app import create_app
    from entorhinal.runtime.config import RuntimeConfig, SourceSpec
    from entorhinal.runtime.factory import build_runtime
    from entorhinal.runtime.sources import registered_adapters

    root = Path(storage_dir) if storage_dir else Path.home() / ".entorhinal"
    specs: list[SourceSpec] = []
    for item in source or []:
        key, _, name = item.partition(":")
        key = key.strip()
        name = name.strip() or key
        if not key:
            console.print("[bold red]Invalid --source value (empty registry key).[/bold red]")
            raise typer.Exit(code=1)
        specs.append(SourceSpec(name=name, adapter=key))

    # No silent auto-configuration: a producer starts only from explicit
    # --source/--source-opt. Bare --wire-sources serves the API with a
    # truthful no-producer message instead of failing on missing options.
    options_by_name: dict[str, dict] = {}
    for opt in source_opt or []:
        name_key, sep, value = opt.partition("=")
        if not sep or not name_key.strip():
            console.print(f"[bold red]Invalid --source-opt value {opt!r}; expected '<name>.<key>=<value>'.[/bold red]")
            raise typer.Exit(code=1)
        # Source names may contain dots: match the longest configured source
        # name that prefixes '<name>.<key>' instead of splitting first-dot.
        match = ""
        for spec in specs:
            prefix = spec.name + "."
            if name_key.startswith(prefix) and len(spec.name) > len(match):
                match = spec.name
        if not match:
            console.print(f"[bold red]--source-opt for unconfigured source in {opt!r}; "
                          f"configured: {sorted(s.name for s in specs) or 'none'}.[/bold red]")
            raise typer.Exit(code=1)
        key = name_key[len(match) + 1:]
        if not key.strip():
            console.print(f"[bold red]Invalid --source-opt value {opt!r}; expected '<name>.<key>=<value>'.[/bold red]")
            raise typer.Exit(code=1)
        options_by_name.setdefault(match, {})[key.strip()] = value
    if options_by_name:
        remapped: list[SourceSpec] = []
        for spec in specs:
            extra = options_by_name.get(spec.name, {})
            remapped.append(SourceSpec(
                name=spec.name, adapter=spec.adapter,
                enabled=spec.enabled, options={**spec.options, **extra},
            ))
        specs = remapped
        unknown = set(options_by_name) - {s.name for s in specs}
        if unknown:
            console.print(f"[bold red]--source-opt for unconfigured source(s): {sorted(unknown)}.[/bold red]")
            raise typer.Exit(code=1)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s: %(message)s",
    )
    config = RuntimeConfig.from_root(root, sources=specs)
    runtime = build_runtime(config)
    fastapi_app = create_app(runtime=runtime)

    console.print(f"[bold cyan]Starting Entorhinal Context Daemon on http://{host}:{port} ...[/bold cyan]")
    console.print(f"[bold green]Trust UI available at http://{host}:{port}/ui[/bold green]")
    console.print(f"Runtime root: {root} (SQLite store: {config.db_path.name})")
    try:
        from entorhinal.runtime.auth import AuthStore

        if not AuthStore(config.auth_path).list_principals():
            console.print("[bold yellow]Auth store is empty: run 'entorhinal auth bootstrap --dir "
                          f"{root}' to create the first admin; until then all HTTP "
                          "disclosure routes return 401.[/bold yellow]")
    except Exception as e:
        console.print(f"[bold yellow]Auth store unreadable ({e}); disclosure routes may return 401.[/bold yellow]")
    if wire_sources:
        if specs:
            console.print(f"[bold green]Source wiring: starting {len(specs)} adapter(s): "
                          + ", ".join(f"{s.name} ({s.adapter})" for s in specs) + "[/bold green]")
        else:
            console.print("[bold yellow]Source wiring requested but no source adapter is configured; "
                          "serving API only (no producer running).[/bold yellow]")
    else:
        console.print("Source wiring: OFF (API only; use --wire-sources --source <key> to start a producer)")

    if reload:
        console.print("[yellow]Note: --reload is disabled when serving the durable runtime; ignoring.[/yellow]")

    uvicorn_config = uvicorn.Config(fastapi_app, host=host, port=port, log_level="info")
    server = uvicorn.Server(uvicorn_config)

    async def _serve() -> None:
        if wire_sources and specs:
            try:
                await runtime.start_sources()
            except Exception as e:
                console.print(f"[bold red]Failed to start configured sources: {e}[/bold red]")
                runtime.close()
                raise typer.Exit(code=1)
            health = runtime.sources.health()
            for name, detail in health["sources"].items():
                state = "healthy" if detail.get("is_healthy") else "UNHEALTHY"
                console.print(f"  source {name}: {state}")
        try:
            await server.serve()
        finally:
            if wire_sources and specs:
                await runtime.stop_sources()
                console.print("[cyan]Source adapters stopped cleanly.[/cyan]")
            runtime.close()

    try:
        asyncio.run(_serve())
    except KeyboardInterrupt:
        console.print("[yellow]Daemon shutdown requested.[/yellow]")


@app.command("serve-vnext")
def serve_vnext(
    storage_dir: Optional[str] = typer.Option(None, "--dir", "-d", help="Data directory path"),
) -> None:
    """Start the vNext Named Pipe Provider daemon."""
    journal, policy, compiler, user_control = get_default_services(storage_dir)
    
    from entorhinal.query.service import ContextSnapshotService
    from entorhinal.api.vnext_provider import VNextProvider
    from entorhinal.ports.named_pipe import VNextProviderServer
    
    service = ContextSnapshotService(
        compiler=compiler,
        policy_engine=policy,
        journal=journal,
    )
    
    provider = VNextProvider(service)
    server = VNextProviderServer(provider.handle_request)
    
    async def run_server():
        await server.start()
        logger.info("vNext Named Pipe Provider running. Press Ctrl+C to stop.")
        while True:
            await asyncio.sleep(3600)
            
    try:
        import sys
        if sys.platform == 'win32':
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        asyncio.run(run_server())
    except KeyboardInterrupt:
        console.print("[yellow]Shutting down vNext Provider...[/yellow]")
        asyncio.run(server.stop())


if __name__ == "__main__":
    app()
