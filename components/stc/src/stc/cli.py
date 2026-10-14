"""Click and Rich Command-Line Interface for STC."""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import logging
import math
import os
import re
import shutil
import subprocess
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any, Final, cast

import click
import yaml
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from stc import __version__
from stc.compiler.bundler import MAX_BUNDLE_BYTES, ContextCompiler
from stc.core.config import get_settings
from stc.core.errors import (
    BundleSizeExceededError,
    TraceMemoryError,
    WorktreeError,
    WorktreeLeaseActiveError,
)
from stc.genome.store import GenomeStore
from stc.judiciary.auditor import WORKER_CONSTRAINTS, JudiciaryAuditor
from stc.memory.trace_client import TraceClient
from stc.orchestrator.dispatch import (
    ChaperoneWorker,
    ConfinementViolationError,
    dispatch_worker,
)
from stc.protocols.interfaces import (
    SocraticDecomposerProtocol,
    TraceMemoryProtocol,
)
from stc.schemas.models import (
    ArchetypeOption,
    ConcernDimension,
    ExecutionReceipt,
    FileTarget,
    GeneType,
    GenomeAtom,
    JudiciaryVerdict,
    SpecAtom,
    TaskBundle,
    TreeOfConcerns,
    WorktreeLease,
)
from stc.schemas.stl import TaskSpec
from stc.services.engine import STCEngine
from stc.socratic.ambiguity import TAU
from stc.socratic.decomposer import SocraticDecomposer
from stc.substrate.receipt import save_receipt
from stc.substrate.runner import SubstrateRunner
from stc.worktree.manager import WorktreeManager

logger = logging.getLogger(__name__)
console = Console()


def _load_and_validate_spec(spec_path: Path) -> SpecAtom:
    """Read a specification file, compute its checksum, and produce a SpecAtom."""
    if not spec_path.is_file():
        raise click.ClickException(f"Specification file not found: {spec_path}")
    raw_content = spec_path.read_text(encoding="utf-8")
    if len(raw_content.strip()) < 10:
        raise click.ClickException(
            f"Specification content in {spec_path} is too short (min 10 characters)"
        )
    sha256 = hashlib.sha256(raw_content.encode("utf-8")).hexdigest()
    spec_id = spec_path.stem.lower().replace(" ", "_").replace("-", "_")
    return SpecAtom(
        spec_id=spec_id,
        source_path=str(spec_path),
        raw_content=raw_content,
        content_sha256=sha256,
    )


def _decompose_spec_to_toc(atom: SpecAtom) -> TreeOfConcerns:
    """Decompose specification text into a 5-dimensional Tree of Concerns."""
    decomposer: SocraticDecomposerProtocol = SocraticDecomposer()
    return decomposer.decompose(atom)


def _extract_spec_metadata(
    raw_content: str,
) -> tuple[list[FileTarget], list[str], list[str], list[str]]:
    """Extract target files, membrane protocols, invariants, and inhibitors from spec."""
    files: list[FileTarget] = []
    seen_files: set[str] = set()
    for fp in re.findall(r"[`'\"]([a-zA-Z0-9_\-/\\]+\.py)[`'\"]", raw_content):
        normalized = fp.replace("\\", "/")
        if normalized not in seen_files:
            seen_files.add(normalized)
            files.append(FileTarget(path=normalized, action="modify"))

    proto_matches = re.findall(r"([A-Z][a-zA-Z0-9]+Protocol)", raw_content)
    protocols = sorted(set(proto_matches))

    invariants: list[str] = []
    inhibitors: list[str] = []
    for line in raw_content.splitlines():
        line_clean = line.strip().lstrip("#*- ").strip()
        if (
            any(k in line.lower() for k in ["invariant", "must", "rule", "guarantee"])
            and line_clean
        ):
            invariants.append(line_clean[:100])
        if (
            any(k in line.lower() for k in ["prohibit", "forbidden", "disallowed", "never"])
            and line_clean
        ):
            inhibitors.append(line_clean[:100])

    return files[:5], protocols[:5], invariants[:5], inhibitors[:5]


def _compile_bundle(
    atom: SpecAtom,
    task_id: str,
    epoch_index: int = 1,
    target_files: list[FileTarget] | None = None,
    membrane_protocols: list[str] | None = None,
    trace_memory: TraceMemoryProtocol | None = None,
    negative_inhibitors: list[str] | None = None,
) -> tuple[TaskBundle, int, str]:
    """Compile an atomic TaskBundle and enforce the 25KB ceiling via ContextCompiler."""
    toc = _decompose_spec_to_toc(atom)
    compiler = ContextCompiler(trace_memory=trace_memory)
    try:
        return compiler.compile_bundle(
            task_id=task_id,
            spec=atom,
            toc=toc,
            inhibitors=negative_inhibitors or [],
            epoch_index=epoch_index,
            target_files=target_files,
            membrane_protocols=membrane_protocols,
        )
    except (BundleSizeExceededError, TraceMemoryError) as exc:
        raise click.ClickException(str(exc)) from exc


def _dim_status(dim: ConcernDimension) -> str:
    """Format dimension status label for TOC table."""
    return "LOCKED" if dim.dimension_name == "domain_invariants" else "VERIFIED"


@click.group()
@click.version_option(__version__, "-V", "--version", prog_name="stc")
@click.option("-v", "--verbose", is_flag=True, help="Enable verbose debug logging.")
@click.option("-j", "--json", "json_mode", is_flag=True, help="Output machine-readable JSON.")
@click.option("-r", "--root", default=".", type=click.Path(path_type=Path), help="Repository root.")
@click.option("--trace-db", "trace_db", type=click.Path(path_type=Path), help="Explicit Trace DB.")
@click.pass_context
def main(
    ctx: click.Context,
    verbose: bool,
    json_mode: bool,
    root: Path,
    trace_db: Path | None,
) -> None:
    """STC - Biomimetic Spec-To-Code Autonomous Engineering Engine."""
    ctx.ensure_object(dict)
    ctx.obj["VERBOSE"] = verbose
    ctx.obj["JSON_MODE"] = json_mode
    ctx.obj["ROOT"] = root
    ctx.obj["TRACE_DB"] = trace_db
    ctx.obj["settings"] = get_settings()
    ctx.obj["engine"] = STCEngine(ctx.obj["settings"])


@main.command("info")
def info_cmd() -> None:
    """Display STC architectural and runtime environment metadata."""
    table = Table(title="STC: Spec-To-Code Autonomous Engineering Engine", show_header=True)
    table.add_column("Property", style="cyan", no_wrap=True)
    table.add_column("Value", style="green")

    table.add_row("Version", __version__)
    table.add_row("Python Target", ">=3.12")
    table.add_row("Architecture", "Biomimetic Spec-To-Code (Hexagonal + Trias Politica)")
    table.add_row("Context Ceiling", "25,600 Bytes (25 KB)")
    table.add_row("Quality Standards", "Ruff + Mypy Strict + Pytest + Mutmut (0% Mock Policy)")

    console.print(table)


@main.command("manual-template")
@click.argument("role", type=click.Choice(["diverge", "refine", "synthesize", "critique"]))
def manual_template_cmd(role: str) -> None:
    """Print the canonical manual-handoff payload template for a role."""
    from stc.integration.manual_payloads import render_template

    click.echo(render_template(role), nl=False)


@main.command("health")
@click.option("--json-output", is_flag=True, help="Output health status as raw JSON.")
@click.pass_context
def health_cmd(ctx: click.Context, json_output: bool) -> None:
    """Check health and readiness of the STC runtime engine."""
    engine: STCEngine = ctx.obj["engine"]
    status = asyncio.run(engine.check_health())

    if json_output or ctx.obj.get("JSON_MODE"):
        click.echo(status.model_dump_json(indent=2))
        return

    color = "green" if status.status == "ok" else "red"
    console.print(
        Panel(
            f"[bold {color}]Status: {status.status.upper()}[/bold {color}]\n"
            f"Service: {status.service} v{status.version}\n"
            f"Timestamp: {status.timestamp.isoformat()}\n"
            f"Active Workers: {status.metrics.active_workers}\n"
            f"Tasks Succeeded: {status.metrics.tasks_succeeded}",
            title="STC Health Diagnostics",
            border_style=color,
        )
    )


@main.command("run-task")
@click.option("--action", default="ping", help="Action to execute (ping, echo, compute).")
@click.option("--name", default="cli-task", help="Human-readable task name.")
@click.option("--spec-file", type=click.Path(exists=True, path_type=Path), help="YAML task spec.")
@click.pass_context
def run_task_cmd(ctx: click.Context, action: str, name: str, spec_file: Path | None) -> None:
    """Execute an atomic task via the STC service engine."""
    engine: STCEngine = ctx.obj["engine"]

    if spec_file:
        with spec_file.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        spec = TaskSpec.model_validate(data)
    else:
        spec = TaskSpec(name=name, action=action)

    console.print(f"[bold cyan]Running Task:[/bold cyan] {spec.name} ({spec.action})")
    receipt = asyncio.run(engine.run_task(spec))

    if ctx.obj.get("JSON_MODE"):
        click.echo(receipt.model_dump_json(indent=2))
        return

    console.print(f"[bold green][+] Task {receipt.status.value.upper()}[/bold green]")
    console.print(f"  - Receipt ID: {receipt.receipt_id}")
    console.print(f"  - Duration: {receipt.duration_ms} ms")
    console.print(f"  - Checksum: {receipt.checksum_sha256[:16]}...")


@main.command("spec")
@click.argument("spec_path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.pass_context
def spec_cmd(ctx: click.Context, spec_path: Path) -> None:
    """Ingest and decompose a specification into a Tree of Concerns (TOC)."""
    atom = _load_and_validate_spec(spec_path)
    decomposer: SocraticDecomposerProtocol = SocraticDecomposer()
    toc = decomposer.decompose(atom)
    diffs = decomposer.detect_ambiguity(toc)

    if ctx.obj.get("JSON_MODE"):
        payload = {
            "spec_atom": atom.model_dump(mode="json"),
            "tree_of_concerns": toc.model_dump(mode="json"),
            "ambiguity_detected": bool(diffs),
            "archetype_diffs": [d.model_dump(mode="json") for d in diffs],
        }
        click.echo(json.dumps(payload, indent=2))
        return

    console.print(
        Panel(f"[bold cyan]Ingesting Specification:[/bold cyan] {spec_path}", expand=False)
    )
    toc_table = Table(title="Tree of Concerns (TOC) Decomposition", show_header=True)
    toc_table.add_column("Dimension", style="cyan")
    toc_table.add_column("Status", style="green")
    toc_table.add_column("Extracted Atoms", style="white")

    toc_table.add_row(
        "Domain Invariants",
        _dim_status(toc.domain_invariants),
        f"{len(toc.domain_invariants.invariants)} rules detected",
    )
    toc_table.add_row(
        "Persistence & Storage",
        _dim_status(toc.persistence_storage),
        f"{len(toc.persistence_storage.contracts)} contracts parsed",
    )
    toc_table.add_row(
        "Communication Protocols",
        _dim_status(toc.communication_protocols),
        f"{len(toc.communication_protocols.contracts)} contracts parsed",
    )
    toc_table.add_row(
        "Boundary & Security",
        _dim_status(toc.boundary_security),
        f"{len(toc.boundary_security.contracts)} policies parsed",
    )
    toc_table.add_row(
        "Failure Resilience",
        _dim_status(toc.failure_resilience),
        f"{len(toc.failure_resilience.failure_modes)} failure policies parsed",
    )

    console.print(toc_table)

    if diffs:
        console.print(
            f"Ambiguity Score: {toc.ambiguity_score:.2f} [THRESHOLD EXCEEDED: >= {TAU:.2f}]"
        )
        console.print(
            f"\n[bold yellow][!] High ambiguity detected ({toc.ambiguity_score:.2f}). "
            f"Threshold >= {TAU:.2f}. ArchetypeDiff required.[/bold yellow]"
        )
        selected_choices: list[int] = []
        chosen_options: list[ArchetypeOption] = []
        for diff in diffs:
            console.print(
                f"\n[bold yellow][?] ARCHETYPE DILEMMA DETECTED:[/bold yellow] "
                f"[bold white]{diff.core_dilemma}[/bold white]"
            )
            console.print(f"  (1) [bold cyan]{diff.option_a.title}:[/bold cyan]")
            console.print(f"      Pro: {diff.option_a.tradeoff_pro}")
            console.print(f"      Con: {diff.option_a.tradeoff_con}")
            for inv in diff.option_a.invariants_to_lock:
                console.print(f"      Invariant: {inv}")
            console.print(f"  (2) [bold cyan]{diff.option_b.title}:[/bold cyan]")
            console.print(f"      Pro: {diff.option_b.tradeoff_pro}")
            console.print(f"      Con: {diff.option_b.tradeoff_con}")
            for inv in diff.option_b.invariants_to_lock:
                console.print(f"      Invariant: {inv}")

            try:
                choice = click.prompt(
                    "\nSelect choice [1/2]",
                    type=click.Choice(["1", "2"]),
                    default="1",
                    show_default=True,
                )
            except click.Abort as exc:
                raise click.ClickException(
                    "Sovereign choice aborted (timeout/abort) — routed to "
                    "CIRCUIT_FAIL per 02_EXECUTION_DAG.md N05; no invariant locked."
                ) from exc
            selected_idx = int(choice)
            selected_choices.append(selected_idx)
            chosen_option = diff.option_b if selected_idx == 2 else diff.option_a
            chosen_options.append(chosen_option)

        locked_path = decomposer.lock_invariants(toc, selected_choices)
        for chosen_option in chosen_options:
            for inv in chosen_option.invariants_to_lock:
                console.print(f'[bold green][+] Invariant locked: "{inv}"[/bold green]')
        console.print(f"[bold green][+] Written to {locked_path}[/bold green]")
    else:
        console.print(
            "\n[bold green][+] Specification validated with zero ambiguous dilemmas.[/bold green]"
        )


@main.command("compile")
@click.argument("task_id")
@click.option("--spec", "spec_path", required=True, type=click.Path(exists=True, path_type=Path))
@click.option(
    "--out",
    "out_path",
    default=Path("./artifacts/task_bundle.yaml"),
    type=click.Path(path_type=Path),
)
@click.option("--trace-db", "trace_db", type=click.Path(path_type=Path), help="Explicit Trace DB.")
@click.option("--target-file", "target_files", multiple=True, help="Target file path to modify.")
@click.option(
    "--protocol",
    "membrane_protocols",
    multiple=True,
    help="Membrane typing protocol to include.",
)
@click.pass_context
def compile_cmd(
    ctx: click.Context,
    task_id: str,
    spec_path: Path,
    out_path: Path,
    trace_db: Path | None,
    target_files: tuple[str, ...],
    membrane_protocols: tuple[str, ...],
) -> None:
    """Compile a sub-25KB task bundle from Neocortex invariants and Hippocampal traces."""
    atom = _load_and_validate_spec(spec_path)
    custom_targets = (
        [FileTarget(path=tf, action="modify") for tf in target_files] if target_files else None
    )
    custom_protocols = list(membrane_protocols) if membrane_protocols else None
    toc = _decompose_spec_to_toc(atom)

    db_path = trace_db or ctx.obj.get("TRACE_DB") or ctx.obj.get("settings").trace_db_path
    trace_client = TraceClient(db_path=db_path)
    compiler = ContextCompiler(trace_memory=trace_client)

    try:
        bundle, byte_size, yaml_str = compiler.compile_bundle(
            task_id=task_id,
            spec=atom,
            toc=toc,
            inhibitors=[],
            target_files=custom_targets,
            membrane_protocols=custom_protocols,
        )
        pruned_traces = compiler.last_pruned_traces_count
    except (BundleSizeExceededError, TraceMemoryError) as exc:
        raise click.ClickException(str(exc)) from exc

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(yaml_str, encoding="utf-8")

    if ctx.obj.get("JSON_MODE"):
        click.echo(bundle.model_dump_json(indent=2))
        return

    if pruned_traces > 0:
        init_size = compiler.initial_bundle_bytes or byte_size
        console.print(
            f"[bold red][!] CRITICAL: Task bundle size ({init_size:,} bytes) "
            f"exceeds {compiler.max_bundle_bytes:,} byte ceiling![/bold red]"
        )
        console.print("  [-] Hierarchical context pruning triggered...")
        console.print(f"  [+] Pruned {pruned_traces} redundant historical traces.")
        console.print(f"  [+] Final bundle size: {byte_size:,} bytes. (PASS)")
        console.print(f"[bold green][+] Saved to {out_path}[/bold green]")
    else:
        console.print(f"[bold cyan]Compiling Task Bundle:[/bold cyan] {task_id}")
        console.print(f"  - Source Spec: {spec_path}")
        console.print(f"  - Target Output: {out_path}")
        console.print(
            f"  - Context byte budget (<{compiler.max_bundle_bytes:,} bytes): "
            f"[bold green]PASS ({byte_size}B)[/bold green]"
        )
        console.print(f"[bold green][+] Bundle successfully compiled to {out_path}[/bold green]")


@main.group("worktree")
def worktree_group() -> None:
    """Manage ephemeral leased Git worktrees for executive workers."""


@worktree_group.command("lease")
@click.argument("task_id")
@click.option("--branch", default=None, help="Target branch name.")
@click.option("--epoch", default=1, type=int, help="Epoch index.")
# Branch point (re-specified per section 5.3): explicit user input for an
# off-evaluation-path CLI op; the evaluation path never reads this.
@click.option("--base-branch", default="main", help="Base branch name.")
@click.pass_context
def worktree_lease_cmd(
    ctx: click.Context, task_id: str, branch: str | None, epoch: int, base_branch: str
) -> None:
    """Allocate an isolated Git worktree lease."""
    repo_root = Path.cwd()
    mgr = WorktreeManager(repo_root=repo_root)
    try:
        lease = mgr.allocate_lease(
            task_id=task_id, epoch=epoch, base_branch=base_branch, branch=branch
        )
    except (WorktreeError, WorktreeLeaseActiveError) as exc:
        raise click.ClickException(str(exc)) from exc

    if ctx.obj.get("JSON_MODE"):
        click.echo(lease.model_dump_json(indent=2))
        return

    console.print(
        f"[bold green][+] Allocated worktree lease for {task_id} on "
        f"{lease.branch_name}[/bold green]"
    )
    console.print(f"  - Worktree Path: {lease.worktree_path}")
    console.print(f"  - Expires At: {lease.expires_at.isoformat()}")


@worktree_group.command("list")
@click.pass_context
def worktree_list_cmd(ctx: click.Context) -> None:
    """List all active Git worktree leases."""
    repo_root = Path.cwd()
    mgr = WorktreeManager(repo_root=repo_root)
    try:
        leases = mgr.list_leases()
        if ctx.obj.get("JSON_MODE"):
            click.echo(json.dumps([item.model_dump(mode="json") for item in leases], indent=2))
            return
        if leases:
            table = Table(title="Active Worktree Leases", show_header=True)
            table.add_column("Task ID", style="cyan")
            table.add_column("Branch", style="white")
            table.add_column("Worktree Path", style="yellow")
            table.add_column("Expires At", style="green")
            for item in leases:
                table.add_row(
                    item.task_id,
                    item.branch_name,
                    str(item.worktree_path),
                    item.expires_at.isoformat(),
                )
            console.print(table)
            return
        console.print("[dim]No active worktree leases currently allocated.[/dim]")
    except (WorktreeError, FileNotFoundError):
        if ctx.obj.get("JSON_MODE"):
            click.echo("[]")
            return
        console.print("[dim]No active worktree leases currently allocated.[/dim]")


@worktree_group.command("release")
@click.argument("task_id")
@click.option("--purge", is_flag=True, help="Force remove directory and delete branch.")
@click.pass_context
def worktree_release_cmd(ctx: click.Context, task_id: str, purge: bool) -> None:
    """Release and clean up an active Git worktree lease."""
    repo_root = Path.cwd()
    mgr = WorktreeManager(repo_root=repo_root)
    try:
        res = mgr.release_by_task_id(task_id, purge=purge)
        if ctx.obj.get("JSON_MODE"):
            click.echo(json.dumps(res, indent=2))
            return
        if res["status"] == "RELEASED":
            console.print(f"[bold green][+] Released worktree lease for {task_id}[/bold green]")
        else:
            console.print(f"[bold yellow][!] Worktree status: {res['status']}[/bold yellow]")
    except (WorktreeError, FileNotFoundError) as exc:
        raise click.ClickException(str(exc)) from exc


@main.command("gate")
@click.argument("task_id")
@click.option(
    "--path",
    "worktree_path",
    default=Path(),
    type=click.Path(exists=True, path_type=Path),
    help="Target directory or worktree to evaluate.",
)
@click.option("--epoch", default=1, type=int, help="Task iteration epoch (1-3).")
@click.pass_context
def gate_cmd(ctx: click.Context, task_id: str, worktree_path: Path, epoch: int) -> None:
    """Execute deterministic mechanical quality gates (Ruff, Mypy, Pytest, Mutmut)."""
    runner = SubstrateRunner()
    console.print(f"[bold cyan]Executing Substrate Quality Gates on {task_id}...[/bold cyan]")

    receipt = runner.execute_gates(
        worktree_path=worktree_path,
        task_id=task_id,
        epoch_index=epoch,
    )
    receipt_path = runner.save_receipt(receipt)

    if ctx.obj.get("JSON_MODE"):
        click.echo(receipt.model_dump_json(indent=2))
        if not receipt.is_passing:
            raise click.ClickException("Substrate gates failed.")
        return

    table = Table(title=f"Substrate Quality Gates Report: {task_id}", show_header=True)
    table.add_column("Gate Name", style="cyan")
    table.add_column("Exit Code", style="white")
    table.add_column("Duration (s)", style="white")
    table.add_column("Violations", style="white")
    table.add_column("Status", style="bold")

    for gate in [
        receipt.gate_ruff,
        receipt.gate_mypy,
        receipt.gate_pytest,
        receipt.gate_mutmut,
    ]:
        status_style = "green" if gate.exit_code == 0 else "red"
        status_text = "PASS" if gate.exit_code == 0 else "FAIL"
        table.add_row(
            gate.gate_name.upper(),
            str(gate.exit_code),
            f"{gate.duration_seconds:.3f}",
            str(gate.violations_count),
            f"[{status_style}]{status_text}[/{status_style}]",
        )

    console.print(table)
    console.print(f"  - Receipt Saved: {receipt_path}")
    console.print(f"  - SHA-256 Signature: {receipt.sha256_signature[:24]}...")

    if receipt.is_passing:
        console.print("[bold green][+] All Substrate Gates PASSED. Receipt signed.[/bold green]")
    else:
        console.print("[bold red][-] Quality Gate Failure: Exit code != 0 detected.[/bold red]")
        raise click.ClickException("Substrate gate verification failed.")


@main.command("judge")
@click.argument("task_id")
@click.option(
    "--receipt", "receipt_path", required=True, type=click.Path(exists=True, path_type=Path)
)
@click.option(
    "--bundle",
    "bundle_path",
    default=None,
    type=click.Path(exists=True, path_type=Path),
    help="Optional TaskBundle path. Defaults to artifacts/task_bundle.yaml if present.",
)
@click.option(
    "--diff",
    "diff_path",
    default=None,
    type=click.Path(exists=True, path_type=Path),
    help="Optional path to git diff file to audit.",
)
@click.option(
    "--worktree",
    "worktree_path",
    default=None,
    type=click.Path(exists=True, path_type=Path),
    help="Optional worktree path to extract diff from.",
)
@click.option(
    "--with-codex",
    is_flag=True,
    help="Explicitly verify OpenAI Codex CLI execution runtime.",
)
@click.pass_context
def judge_cmd(
    ctx: click.Context,
    task_id: str,
    receipt_path: Path,
    bundle_path: Path | None,
    diff_path: Path | None,
    worktree_path: Path | None,
    with_codex: bool,
) -> None:
    """Trigger a blind adversarial judiciary audit via JudiciaryAuditor and Codex CLI."""
    if not receipt_path.is_file():
        raise click.ClickException(f"Receipt file not found: {receipt_path}")

    raw = receipt_path.read_text(encoding="utf-8")
    receipt_data = json.loads(raw)
    receipt = ExecutionReceipt.model_validate(receipt_data)

    runner = SubstrateRunner()
    if not runner.verify_receipt(receipt):
        raise click.ClickException(
            "Cryptographic signature check FAILED: Receipt has been tampered with or is corrupted."
        )

    if not receipt.is_passing:
        raise click.ClickException(
            "Judiciary Audit REJECTED: Candidate failed deterministic substrate gates."
        )

    bundle: TaskBundle
    if bundle_path and bundle_path.is_file():
        b_data = yaml.safe_load(bundle_path.read_text(encoding="utf-8"))
        bundle = TaskBundle.model_validate(b_data)
    elif Path("artifacts/task_bundle.yaml").is_file():
        b_data = yaml.safe_load(Path("artifacts/task_bundle.yaml").read_text(encoding="utf-8"))
        if isinstance(b_data, dict) and b_data.get("task_id") == task_id:
            bundle = TaskBundle.model_validate(b_data)
        else:
            bundle = TaskBundle(
                task_id=task_id,
                epoch_index=receipt.epoch_index,
                spec_id="spec_inferred",
                goal_statement=(
                    f"Audit candidate implementation {task_id} against Neocortex invariants"
                ),
                invariants=["Zero mock certification policy", "Deterministic exit code 0 required"],
                target_files=[],
                membrane_protocols=[],
                negative_inhibitors=[],
                correlation_id=receipt.correlation_id,
                causation_id=receipt.causation_id,
            )
    else:
        bundle = TaskBundle(
            task_id=task_id,
            epoch_index=receipt.epoch_index,
            spec_id="spec_inferred",
            goal_statement=f"Audit candidate implementation {task_id} against Neocortex invariants",
            invariants=["Zero mock certification policy", "Deterministic exit code 0 required"],
            target_files=[],
            membrane_protocols=[],
            negative_inhibitors=[],
            correlation_id=receipt.correlation_id,
            causation_id=receipt.causation_id,
        )

    codex_bin = shutil.which("codex") or shutil.which("codex.exe")
    if not codex_bin:
        local_app = os.environ.get("LOCALAPPDATA")
        if local_app:
            candidate = Path(local_app) / "Programs" / "OpenAI" / "Codex" / "bin" / "codex.exe"
            if candidate.is_file():
                codex_bin = str(candidate)
    if not codex_bin:
        codex_default = Path("C:/Users/anshu/AppData/Local/Programs/OpenAI/Codex/bin/codex.exe")
        if codex_default.is_file():
            codex_bin = str(codex_default)

    if with_codex and not codex_bin:
        raise click.ClickException(
            "Adversarial Judiciary requires OpenAI Codex CLI ('codex.exe') on system PATH."
        )

    auditor = JudiciaryAuditor(
        runner=runner,
        with_codex=with_codex,
        codex_bin=codex_bin,
    )
    if diff_path and diff_path.is_file():
        diff_text = diff_path.read_text(encoding="utf-8")
    elif worktree_path:
        diff_text = auditor.extract_worktree_diff(worktree_path)
    else:
        diff_text = ""
    verdict = auditor.audit_diff(diff_text=diff_text, bundle=bundle, receipt=receipt)

    if ctx.obj.get("JSON_MODE"):
        click.echo(verdict.model_dump_json(indent=2))
        if verdict.status != "APPROVED":
            raise click.ClickException(
                f"Judiciary Audit {verdict.status}: {verdict.summary_rationale}"
            )
        return

    console.print(
        f"[bold magenta]Dispatching Blind Judiciary Auditor for {task_id}...[/bold magenta]"
    )
    console.print(f"  - Verified Receipt: {receipt.receipt_id} (Signature Bit-Exact)")
    if codex_bin:
        console.print(f"  - Codex Engine Binary: {codex_bin}")

    if verdict.findings:
        find_table = Table(title="Judiciary Audit Findings", show_header=True)
        find_table.add_column("Rule", style="cyan")
        find_table.add_column("Severity", style="red")
        find_table.add_column("Filepath", style="white")
        find_table.add_column("Snippet", style="yellow")
        for f in verdict.findings:
            find_table.add_row(f.rule_name, f.severity, f.filepath, f.snippet[:60])
        console.print(find_table)

    if verdict.status == "APPROVED":
        console.print(f"[bold green]VERDICT: APPROVED[/bold green] ({verdict.summary_rationale})")
    elif verdict.status == "QUARANTINED":
        console.print(
            f"[bold yellow]VERDICT: QUARANTINED[/bold yellow] ({verdict.summary_rationale})"
        )
        raise click.ClickException(f"Judiciary Audit QUARANTINED: {verdict.summary_rationale}")
    elif verdict.status == "REJECTED":
        console.print(f"[bold red]VERDICT: REJECTED[/bold red] ({verdict.summary_rationale})")
        raise click.ClickException(f"Judiciary Audit REJECTED: {verdict.summary_rationale}")


@main.command("promote")
@click.argument("task_id")
@click.option(
    "--receipt",
    "receipt_path",
    type=click.Path(exists=True, path_type=Path),
    help="Verified ExecutionReceipt path.",
)
# Branch point (re-specified per section 5.3): explicit user input for an
# off-evaluation-path CLI op; the evaluation path never reads this.
@click.option(
    "--base-branch",
    default="main",
    help="Base branch to merge candidate branch into.",
)
def promote_cmd(task_id: str, receipt_path: Path | None, base_branch: str) -> None:
    """Sovereign merge gate and Project Trace genome ingestion."""
    repo_root = Path.cwd()
    receipt: ExecutionReceipt | None = None
    if receipt_path:
        raw = receipt_path.read_text(encoding="utf-8")
        receipt = ExecutionReceipt.model_validate(json.loads(raw))
        if not SubstrateRunner().verify_receipt(receipt):
            raise click.ClickException(
                "Promotion rejected: Receipt cryptographic signature mismatch."
            )
        if not receipt.is_passing:
            raise click.ClickException("Promotion rejected: Receipt quality gates did not pass.")

    console.print(f"[bold yellow][?] Sovereign Promotion Confirmation for {task_id}[/bold yellow]")
    if not click.confirm("Merge candidate branch to main and ingest genes into Trace DB?"):
        console.print("[red]Promotion cancelled by Sovereign.[/red]")
        return

    manager = WorktreeManager(repo_root=repo_root)
    norm_id = manager._normalize_task_id(task_id)
    records = manager._load_leases()
    lease: WorktreeLease | None = None
    branch_name = f"stc/{norm_id}"
    diff_text = ""
    if norm_id in records:
        rec = records[norm_id]
        lease_fields = {
            "lease_id",
            "task_id",
            "branch_name",
            "worktree_path",
            "leased_at",
            "expires_at",
            "is_active",
        }
        clean_rec = {k: v for k, v in rec.items() if k in lease_fields}
        lease = WorktreeLease.model_validate(clean_rec)
        branch_name = lease.branch_name
        diff_text = manager.get_diff(lease)

    merge_res = subprocess.run(
        [
            "git",
            "merge",
            "--no-ff",
            "-m",
            f"Merge branch '{branch_name}' ({task_id})",
            branch_name,
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if merge_res.returncode != 0:
        subprocess.run(
            ["git", "merge", "--abort"],
            cwd=repo_root,
            capture_output=True,
            check=False,
        )
        raise click.ClickException(
            f"Git merge failed (exit {merge_res.returncode}): "
            f"{merge_res.stderr or merge_res.stdout}. Promotion aborted."
        )

    genome_store = GenomeStore()
    if receipt is not None:
        genes = genome_store.ingest_trace(task_id=task_id, receipt=receipt, diff_text=diff_text)
    else:
        struct_gene = GenomeAtom(
            gene_id=f"gene_struct_{uuid.uuid4().hex[:8]}",
            gene_type=GeneType.STRUCTURAL,
            component_name=task_id,
            pattern_signature=f"structural:{task_id}:promoted",
            raw_code_or_rule=diff_text or f"# Promoted code for {task_id}",
            receipt_reference="rcpt_sovereign_promoted",
        )
        genome_store.save_gene(struct_gene)
        genes = [struct_gene]

    console.print(f"[bold green][+] Merged branch {branch_name} to {base_branch}.[/bold green]")
    console.print(f"[bold green][+] Ingested {len(genes)} genes into Trace Genome DB.[/bold green]")
    if lease:
        manager.release_lease(lease, purge=True)
        console.print(
            f"[bold green][+] Released worktree {lease.worktree_path}. "
            f"Task {task_id} COMPLETED.[/bold green]"
        )
    else:
        console.print(f"[bold green][+] Task {task_id} COMPLETED.[/bold green]")


class CLIChaperoneWorker(ChaperoneWorker):
    """ChaperoneWorker optimized for repository trees by excluding virtualenvs and caches."""

    IGNORED_PARTS = {
        ".git",
        ".venv",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".mutmut-cache",
        "node_modules",
        "__pycache__",
        "mutants",
    }

    def __init__(
        self,
        worker_cmd: list[str] | None = None,
        worker_fn: Callable[[TaskBundle, Path], Any] | None = None,
        enforce_membrane: bool = True,
        allowed_tools: tuple[str, ...] = (
            "agy",
            "aider",
            "dsh",
            "python",
            "pytest",
            "git",
            "ruff",
        ),
    ) -> None:
        def _default_worker(bundle: TaskBundle, root: Path) -> None:
            if worker_fn is not None:
                worker_fn(bundle, root)
            with contextlib.suppress(Exception):
                subprocess.run(
                    ["ruff", "format", "."],
                    cwd=root,
                    capture_output=True,
                    check=False,
                )

        super().__init__(
            worker_cmd=worker_cmd,
            worker_fn=_default_worker,
            enforce_membrane=enforce_membrane,
            allowed_tools=allowed_tools,
        )

    def _snapshot_outer_files(self, root: Path) -> dict[Path, float]:
        outer: dict[Path, float] = {}
        dirs_to_monitor: list[Path] = []
        repo_root = self._find_repo_root(root)
        if repo_root is not None and repo_root.is_dir():
            dirs_to_monitor.append(repo_root)
        if root.parent.is_dir() and root.parent not in dirs_to_monitor:
            dirs_to_monitor.append(root.parent)

        for mon_dir in dirs_to_monitor:
            with contextlib.suppress(OSError, PermissionError):
                for dirpath, dirnames, filenames in os.walk(mon_dir):
                    dirnames[:] = [d for d in dirnames if d not in self.IGNORED_PARTS]
                    p_dir = Path(dirpath)
                    if p_dir.is_relative_to(root):
                        dirnames.clear()
                        continue
                    for d in dirnames:
                        d_item = p_dir / d
                        with contextlib.suppress(OSError, PermissionError):
                            outer[d_item] = d_item.stat().st_mtime
                    for fname in filenames:
                        item = p_dir / fname
                        with contextlib.suppress(OSError, PermissionError):
                            outer[item] = item.stat().st_mtime
        return outer

    def _check_outer_tampering(self, root: Path, before: dict[Path, float]) -> None:
        dirs_to_monitor: list[Path] = []
        repo_root = self._find_repo_root(root)
        if repo_root is not None and repo_root.is_dir():
            dirs_to_monitor.append(repo_root)
        if root.parent.is_dir() and root.parent not in dirs_to_monitor:
            dirs_to_monitor.append(root.parent)

        created_items: list[Path] = []
        modified_files: list[Path] = []

        for mon_dir in dirs_to_monitor:
            with contextlib.suppress(OSError, PermissionError):
                for dirpath, dirnames, filenames in os.walk(mon_dir):
                    dirnames[:] = [d for d in dirnames if d not in self.IGNORED_PARTS]
                    p_dir = Path(dirpath)
                    if p_dir.is_relative_to(root):
                        dirnames.clear()
                        continue
                    for d in dirnames:
                        d_item = p_dir / d
                        if d_item not in before:
                            created_items.append(d_item)
                    for fname in filenames:
                        item = p_dir / fname
                        with contextlib.suppress(OSError, PermissionError):
                            if item not in before:
                                created_items.append(item)
                            elif item.stat().st_mtime > before[item]:
                                modified_files.append(item)

        for c in sorted(created_items, key=lambda p: len(p.parts), reverse=True):
            with contextlib.suppress(OSError):
                if c.is_file() or c.is_symlink():
                    c.unlink()
                elif c.is_dir():
                    c.rmdir()

        if created_items:
            raise ConfinementViolationError(
                f"Worker breached confinement: created path outside lease root: {created_items[0]}"
            )
        if modified_files:
            raise ConfinementViolationError(
                "Worker breached confinement: modified file outside lease root: "
                f"{modified_files[0]}"
            )


def _parse_stc_budget(spec: str | None) -> tuple[dict[str, Any], dict[str, Any]]:
    """Parses --budget k=v pairs into (Budgets kwargs, SearchPolicy kwargs).

    Accepted keys: time, tokens, usd, iters, branching, depth. The token "none"
    clears an optional budget. Defaults mirror SearchPolicy; explicit values
    are recorded in dry-run output and the dossier Q&A log. Explicit zero is
    rejected for the optional budgets: SST's BudgetTracker tests caps for
    truthiness, so 0 would silently mean unlimited — pass "none" instead.
    """
    raw: dict[str, str] = {}
    if spec:
        for chunk in spec.split(","):
            key, sep, val = chunk.partition("=")
            key = key.strip().lower()
            val = val.strip()
            if not sep or key not in {
                "time",
                "tokens",
                "usd",
                "iters",
                "branching",
                "depth",
            }:
                raise click.UsageError(
                    "Invalid --budget (want k=v pairs from "
                    "time,tokens,usd,iters,branching,depth): "
                    f"{spec!r}"
                )
            raw[key] = val

    def _as_int(key: str, default: int) -> int:
        if key not in raw:
            return default
        try:
            value = int(raw[key])
        except ValueError as exc:
            raise click.UsageError(f"Invalid --budget {key}={raw[key]!r}: not an int.") from exc
        if value <= 0:
            raise click.UsageError(f"Invalid --budget {key}={value}: must be positive.")
        return value

    def _as_opt_int(key: str, default: int | None) -> int | None:
        if key not in raw:
            return default
        if raw[key].lower() == "none":
            return None
        return _checked_opt_int(key)

    def _checked_opt_int(key: str) -> int:
        try:
            value = int(raw[key])
        except ValueError as exc:
            raise click.UsageError(f"Invalid --budget {key}={raw[key]!r}: not an int.") from exc
        if value <= 0:
            raise click.UsageError(f"Invalid --budget {key}={value}: must be positive (or 'none').")
        return value

    def _as_opt_float(key: str, default: float | None) -> float | None:
        if key not in raw:
            return default
        if raw[key].lower() == "none":
            return None
        try:
            value = float(raw[key])
        except ValueError as exc:
            raise click.UsageError(f"Invalid --budget {key}={raw[key]!r}: not a number.") from exc
        if value <= 0:
            raise click.UsageError(f"Invalid --budget {key}={value}: must be positive (or 'none').")
        return value

    time_s = _as_int("time", 600)
    tokens = _as_opt_int("tokens", 500000)
    usd = _as_opt_float("usd", 10.0)
    budgets: dict[str, Any] = {
        "time_budget_seconds": time_s,
        "token_budget": tokens,
        "cost_budget_usd": usd,
    }
    policy: dict[str, Any] = {
        "max_iterations": _as_int("iters", 10),
        "branching_factor": _as_int("branching", 3),
        "max_depth": _as_int("depth", 4),
        "max_token_budget": tokens,
        "max_cost_usd": usd,
        "max_time_seconds": time_s,
    }
    return budgets, policy


def _seed_codex_home() -> Path | None:
    """Copies the operator codex login into a writable temp home (P04 pattern).

    The seeded config always carries `model_reasoning_effort = "medium"`
    (winner-carry; see lever comment below). Returns None when no login
    exists (caller fails closed). The caller must delete the returned
    directory. Uses a function-local import so the default DAG path gains no
    new module dependencies.
    """
    import tempfile

    src = Path.home() / ".codex"
    auth, config = src / "auth.json", src / "config.toml"
    if not auth.is_file():
        return None
    try:
        home = Path(tempfile.mkdtemp(prefix="p05-codex-home-"))
        shutil.copy(auth, home / "auth.json")
        (home / "auth.json").chmod(0o600)
        base_cfg = config.read_text(encoding="utf-8") if config.is_file() else ""
        lines: list[str] = []
        replaced = False
        for line in base_cfg.splitlines():
            if line.strip().startswith("model_reasoning_effort"):
                # Winner-carry (live-exp P2-H3a): identical shaped bytes
                # (3339af29…) hang served at reasoning-max (P1-H0b, exit 124
                # @150s) and emit a valid §2 proposal at reasoning-medium in
                # 56.66s; the served header confesses
                # `reasoning effort: medium`. Force medium in the seeded
                # gateway config (argv + SST bytes untouched).
                lines.append('model_reasoning_effort = "medium"')
                replaced = True
            else:
                lines.append(line)
        if not replaced:
            lines.insert(0, 'model_reasoning_effort = "medium"')
        (home / "config.toml").write_text("\n".join(lines) + "\n", encoding="utf-8")
    except OSError:
        return None
    return home


def _sync_seeded_home_back(home: Path | str, main_auth: Path | str | None = None) -> dict[str, Any]:
    """Copy rotated credentials from a seeded scratch home back to the login.

    Closeout repair for the attempt-5 auth orphaning (AUTH-DIAGNOSIS.md):
    `_seed_codex_home` copies `auth.json` out, the CLI rotates the token
    pair inside the scratch home on refresh, and deleting the scratch home
    orphaned the operator login (next run presents an already-used refresh
    token). Call this BEFORE deleting the scratch home.

    Rules (fail closed, metadata only — credential bytes never logged):
    - scratch missing -> "scratch-missing", no write.
    - main login missing -> "main-missing", no write.
    - unreadable side -> "read-error", no write.
    - identical bytes -> "unchanged", no write (covers auth-failed runs:
      no refresh happened, nothing to preserve).
    - differ + scratch strictly newer -> "synced": scratch bytes win
      (this run's own rotation) and replace main atomically (tmp file +
      rename) with mode 0o600.
    - differ + main newer-or-equal, or main changed under us ->
      "main-newer-keep": someone else (e.g. concurrent interactive use)
      rotated after seeding; keep main so a stale scratch copy can
      never regress it.
    - write/rename failure -> "sync-error", main untouched (tmp file
      removed best-effort; a crash may litter `auth.json.sync-tmp`).

    `main_auth` overrides the login path (tests pass tmp paths; production
    passes None for `~/.codex/auth.json`).
    """
    scratch = Path(home) / "auth.json"
    main = Path(main_auth) if main_auth is not None else Path.home() / ".codex" / "auth.json"
    if not scratch.is_file():
        return {"disposition": "scratch-missing", "main": str(main)}
    if not main.is_file():
        return {"disposition": "main-missing", "main": str(main)}
    try:
        scratch_bytes = scratch.read_bytes()
        main_bytes = main.read_bytes()
        scratch_mtime = scratch.stat().st_mtime
        main_mtime = main.stat().st_mtime
    except OSError as exc:
        return {"disposition": "read-error", "error": str(exc)[:100], "main": str(main)}
    record: dict[str, Any] = {
        "main": str(main),
        "main_bytes": len(main_bytes),
        "scratch_bytes": len(scratch_bytes),
        "main_mtime": main_mtime,
        "scratch_mtime": scratch_mtime,
    }
    if scratch_bytes == main_bytes:
        record["disposition"] = "unchanged"
        return record
    if not scratch_mtime > main_mtime:
        record["disposition"] = "main-newer-keep"
        return record
    try:
        if main.stat().st_mtime != main_mtime:
            record["disposition"] = "main-newer-keep"
            return record
        tmp = main.parent / "auth.json.sync-tmp"
        with contextlib.suppress(OSError):
            tmp.unlink()
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(scratch_bytes)
        except BaseException:
            with contextlib.suppress(OSError):
                tmp.unlink()
            raise
        tmp.replace(main)
    except OSError as exc:
        with contextlib.suppress(OSError):
            (main.parent / "auth.json.sync-tmp").unlink(missing_ok=True)
        record["disposition"] = "sync-error"
        record["error"] = str(exc)[:100]
        return record
    record["disposition"] = "synced"
    return record


def _dossier_base_identity(source_root: Path, base_commit: str) -> str:
    """Dossier base identity: commit plus an honest tracked-state label.

    Tracked-only status (the gateway-confinement precedent): untracked
    lease/evidence churn never flips the label. A git failure labels state
    unknown rather than asserting either cleanliness or dirt.
    """
    try:
        proc = subprocess.run(
            ["git", "-C", str(source_root), "status", "--porcelain=v1", "--untracked-files=no"],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return f"{base_commit} + P05 owned (state unknown)"
    if proc.returncode != 0:
        return f"{base_commit} + P05 owned (state unknown)"
    if proc.stdout.strip():
        return f"{base_commit} + P05 owned (uncommitted)"
    return f"{base_commit} (clean)"


#: Mechanical gate discipline for the dialectic path (A4-D1b). Attempt-4
#: pruned on undisclosed mechanics (ruff 100-col E501, mypy --strict
#: annotation/type errors); this product-owned truth rides the bundle so
#: every worker prompt states the enforcing lint/type/test contract.
#: STC-target only: in-lease CLI workers read the enforcing config from
#: the worktree, while text-only gateway emitters see prompt bytes alone.
STC_GATE_DISCIPLINE_INVARIANTS: Final[tuple[str, ...]] = (
    "Gate discipline (ruff): every Python file must pass `ruff check` and "
    "`ruff format --check` with max line length 100.",
    "Gate discipline (mypy): all code must pass `mypy --strict` with full "
    "annotations on every function (no untyped defs).",
    "Gate discipline (pytest): new and changed tests must pass under "
    '`pytest -m "not live"` with zero skipped; live-marked tests never run.',
)


def _gate_timeout_from_env() -> float:
    """Per-gate timeout for the stc target (STC_GATE_TIMEOUT_S).

    Unset/blank keeps the 120s default (behavior unchanged). Explicit
    values must be positive finite seconds; anything else fails fast.
    Liveness bound only — gate set, scope, and thresholds untouched.
    """
    raw = os.environ.get("STC_GATE_TIMEOUT_S", "").strip()
    if not raw:
        return 120.0
    try:
        value = float(raw)
    except ValueError:
        raise click.UsageError(f"STC_GATE_TIMEOUT_S is not a number: {raw!r}.") from None
    if not math.isfinite(value) or value <= 0:
        raise click.UsageError(f"STC_GATE_TIMEOUT_S must be positive seconds: {raw!r}.")
    return value


def _run_stc_target(
    ctx: click.Context,
    *,
    spec_path: Path,
    task_id: str | None,
    yes: bool,
    target: str,
    dry_run: bool,
    manual: bool,
    exec_harness: str | None,
    budget: str | None,
    choice: str | None,
    with_codex: bool,
    pytest_target: str | None,
    base_branch: str,
    max_epochs: int,
) -> None:
    """Executes `run --target stc`: the dialectic loop with dossier output.

    All integration imports are function-local (D14): the default DAG path
    neither imports nor executes any of this. Thin extension over
    DialecticRunner; budgets flow into AdapterContext + SearchPolicy.
    """
    from stc.integration.adapters import AdapterContext, Budgets
    from stc.integration.cli_gateway import CLIGatewayBackend, CLIModelGateway
    from stc.integration.dialectic_runner import (
        ChampionResult,
        DialecticRunner,
    )
    from stc.integration.dossier import (
        assemble_dossier,
        final_outcome,
        new_qa_log,
        write_qa_log,
    )
    from stc.integration.harness_worker import SpendLedger
    from stc.integration.manual_payloads import (
        MANUAL_ROLES,
        role_from_filename,
        validate_payload_text,
    )
    from stc.integration.memory import FileBackedMemory

    _ = target
    if dry_run and manual:
        raise click.UsageError("--dry-run and --manual are mutually exclusive.")
    if exec_harness is not None and dry_run:
        raise click.UsageError("--exec-harness and --dry-run are mutually exclusive.")
    if exec_harness is not None and manual:
        raise click.UsageError("--exec-harness and --manual are mutually exclusive.")
    if with_codex:
        raise click.UsageError("--with-codex conflicts with --target stc (RT-08 audit).")

    json_mode = ctx.obj.get("JSON_MODE", False)
    ignored = [
        name
        for name, used in (
            ("--pytest-target", pytest_target is not None),
            ("--base-branch", base_branch != "main"),
            ("--max-epochs", max_epochs != 3),
        )
        if used
    ]
    if ignored and not json_mode:
        console.print(
            f"[yellow]Note: DAG-only options ignored by --target stc: {', '.join(ignored)}[/yellow]"
        )

    source_root = Path(os.environ.get("STC_SOURCE_ROOT", "") or Path(__file__).resolve().parents[2])
    dossier_dir = Path(os.environ.get("STC_DOSSIER_DIR", "") or Path.cwd() / "dossier")
    dossier_dir.mkdir(parents=True, exist_ok=True)

    commit_proc = subprocess.run(
        ["git", "-C", str(source_root), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    base_commit = commit_proc.stdout.strip() if commit_proc.returncode == 0 else "unknown"
    if base_commit == "unknown" and not json_mode:
        console.print(
            "[yellow]Warning: source root is not a git checkout; base_commit='unknown'.[/yellow]"
        )

    atom = _load_and_validate_spec(spec_path)
    active_task_id = task_id or f"TASK-{atom.spec_id.upper()}"
    decomposer = SocraticDecomposer()
    toc = decomposer.decompose(atom)
    diffs = decomposer.detect_ambiguity(toc, raw_text=atom.raw_content)

    qa_status = "below-tau"
    selected_choices: list[int] = []
    locked_path: Path | None = None
    locked_invariants: list[str] = []
    if diffs:
        if choice is not None:
            selected_choices = [int(choice)] * len(diffs)
        elif yes:
            selected_choices = [1] * len(diffs)
        else:
            qa = new_qa_log(
                spec_id=atom.spec_id,
                ambiguity_score=toc.ambiguity_score,
                tau=TAU,
                status="escalation-required",
                diffs=[
                    {
                        "diff_id": diff.diff_id,
                        "concern_dimension": diff.concern_dimension,
                        "core_dilemma": diff.core_dilemma,
                        "option_a": diff.option_a.model_dump(mode="json"),
                        "option_b": diff.option_b.model_dump(mode="json"),
                    }
                    for diff in diffs
                ],
                note="Autonomous stop: genuine >=tau ambiguity; operator decision required.",
            )
            qa_path = write_qa_log(dossier_dir, qa)
            if json_mode:
                click.echo(
                    json.dumps(
                        {"status": "escalation-required", "qa_log": str(qa_path)},
                        indent=2,
                    )
                )
            else:
                console.print(
                    f"[bold yellow][?] Ambiguity {toc.ambiguity_score:.2f} >= {TAU:.2f} "
                    "— OPERATOR DECISION REQUIRED.[/bold yellow]"
                )
                for diff in diffs:
                    console.print(f"   [yellow]Dilemma:[/yellow] {diff.core_dilemma}")
                    console.print(f"     (1) {diff.option_a.title}: {diff.option_a.tradeoff_pro}")
                    console.print(f"     (2) {diff.option_b.title}: {diff.option_b.tradeoff_pro}")
                console.print(
                    "   Cost of waiting: run paused before any model call; no spend incurred."
                )
                console.print(f"   Recorded: {qa_path}")
                console.print("   Re-run with --choice 1|2 (relay) or --yes (option 1).")
            ctx.exit(2)
        locked_path = decomposer.lock_invariants(
            toc,
            selected_choices,
            output_path=dossier_dir / f"{atom.spec_id.upper()}_INVARIANTS.md",
        )
        for diff, selected in zip(diffs, selected_choices, strict=False):
            picked = diff.option_b if selected == 2 else diff.option_a
            locked_invariants.extend(picked.invariants_to_lock)
        qa_status = "choice-recorded"

    bundle, byte_size, _yaml_str = _compile_bundle(atom, task_id=active_task_id, epoch_index=1)
    if locked_invariants:
        # Escalation chain (RT-09): the recorded choice lands in the downstream
        # bundle as locked invariants (operator decision shaping the run — the
        # legitimate chain, never injected task content).
        bundle = bundle.model_copy(update={"invariants": [*bundle.invariants, *locked_invariants]})
    bundle = bundle.model_copy(
        update={
            "invariants": [
                *bundle.invariants,
                *STC_GATE_DISCIPLINE_INVARIANTS,
                *WORKER_CONSTRAINTS,
            ]
        }
    )
    byte_size = len(ContextCompiler.to_yaml(bundle).encode("utf-8"))
    if byte_size > MAX_BUNDLE_BYTES:
        raise click.ClickException(
            f"Context budget violated: task bundle size ({byte_size} bytes) exceeds "
            f"{MAX_BUNDLE_BYTES} byte ceiling after product-invariant append."
        )
    budgets_kw, policy_kw = _parse_stc_budget(budget)
    budgets = Budgets(**budgets_kw)
    ctx_obj = AdapterContext(
        epoch_index=bundle.epoch_index,
        spec_id=bundle.spec_id,
        budgets=budgets,
        # Wrapper-declared-ignored (P04): substrate gates always run; "true"
        # matches the P04 fixture precedent for this informational field.
        acceptance_commands=("true",),
        source_repo_root=str(source_root),
        base_commit=base_commit,
        adapter_version="P05-1.0",
    )
    # Local import: packet projection needed by dry-run and live alike.
    from stc.integration.adapters import task_bundle_to_packet

    packet = task_bundle_to_packet(bundle, ctx_obj)

    from sst.search.policy import SearchPolicy

    policy = SearchPolicy(**policy_kw)
    substrate = SubstrateRunner(timeout_per_gate=_gate_timeout_from_env())
    auditor = JudiciaryAuditor(runner=substrate, with_codex=False)
    if auditor.with_codex:  # RT-08 tripwire (defense in depth; ctor default is False)
        raise click.ClickException("RT-08 breach: stc-target auditor must use with_codex=False.")

    qa = new_qa_log(
        spec_id=atom.spec_id,
        ambiguity_score=toc.ambiguity_score,
        tau=TAU,
        status=qa_status,
        diffs=(
            [
                {
                    "diff_id": diff.diff_id,
                    "concern_dimension": diff.concern_dimension,
                    "core_dilemma": diff.core_dilemma,
                    "option_a": diff.option_a.model_dump(mode="json"),
                    "option_b": diff.option_b.model_dump(mode="json"),
                }
                for diff in diffs
            ]
            if diffs
            else []
        ),
        selected_choices=selected_choices,
        locked_invariants_path=str(locked_path) if locked_path else None,
        locked_invariants=locked_invariants,
        note="choice recorded via --choice/--yes" if diffs else "no >=tau ambiguity observed",
    )
    write_qa_log(dossier_dir, qa)

    if dry_run:
        if json_mode:
            click.echo(
                json.dumps(
                    {
                        "status": "dry-run",
                        "task_id": active_task_id,
                        "spec_id": atom.spec_id,
                        "bundle_bytes": byte_size,
                        "packet": packet.model_dump(mode="json"),
                        "budgets": budgets_kw,
                        "policy": policy_kw,
                        "with_codex": auditor.with_codex,
                        "model_calls": 0,
                    },
                    indent=2,
                )
            )
        else:
            console.print(f"[bold green]Dry run: {active_task_id} (0 model calls)[/bold green]")
            console.print(f"  Spec: {atom.spec_id} | bundle: {byte_size} bytes")
            console.print(f"  Goal: {packet.goal}")
            console.print(f"  Targets: {', '.join(packet.allowed_paths) or '(none)'}")
            console.print(f"  Source root: {packet.source_repo_root} @ {packet.base_commit}")
            console.print(
                f"  Budgets: time={budgets.time_budget_seconds}s "
                f"tokens={budgets.token_budget} usd={budgets.cost_budget_usd}"
            )
            console.print(
                f"  Policy: iters={policy.max_iterations} "
                f"branching={policy.branching_factor} depth={policy.max_depth}"
            )
            console.print(f"  Audit: with_codex={auditor.with_codex} (RT-08)")
        return

    ledger = SpendLedger(
        dossier_dir / "spend_ledger.jsonl",
        max_worker_calls=60,
        max_gateway_calls=60,
    )
    codex_home: Path | None = None
    limitations: list[str] = []
    try:
        if manual:
            from prompt_kit.harnesses.base import (
                BaseHarness,
                HarnessResult,
            )

            fixture_env = os.environ.get("STC_MANUAL_FIXTURE_DIR", "").strip()

            class _ManualHarness(BaseHarness):
                """Manual/clipboard harness: fixture payloads or operator stdin.

                Every payload is role-validated before submission (Fix 4):
                fixture files at load (fail fast, all errors at once) and
                re-checked at serve time (files may be staged mid-run);
                pastes are re-prompted until they parse to a recognized
                role shape. Invalid packaging fails here with an actionable
                message — never as a candidate-quality failure downstream.
                """

                def __init__(self, payload_dir: Path | None) -> None:
                    super().__init__(name="manual", config={})
                    if payload_dir is None:
                        self._payloads = None
                    else:
                        self._payloads = sorted(
                            p
                            for p in payload_dir.iterdir()
                            if p.is_file() and not p.name.startswith(".")
                        )
                        load_errors: list[str] = []
                        for payload_file in self._payloads:
                            try:
                                text = payload_file.read_text(encoding="utf-8")
                            except OSError as exc:
                                load_errors.append(f"{payload_file.name}: unreadable: {exc}")
                                continue
                            _, problems = validate_payload_text(
                                text,
                                expected_role=role_from_filename(payload_file.name),
                                source=payload_file.name,
                            )
                            load_errors.extend(problems)
                        if load_errors:
                            joined = "\n".join(f"  - {err}" for err in load_errors)
                            raise click.UsageError(
                                "STC_MANUAL_FIXTURE_DIR has invalid payloads:\n"
                                f"{joined}\nTemplates: stc manual-template "
                                f"<{'|'.join(MANUAL_ROLES)}>"
                            )
                    self._index = 0

                def execute(
                    self,
                    prompt: str,
                    role: str = "general",
                    model: str | None = None,
                    context: dict[str, Any] | None = None,
                ) -> HarnessResult:
                    _ = (model, context)
                    if self._payloads is not None:
                        if self._index >= len(self._payloads):
                            return HarnessResult(
                                content="",
                                exit_code=1,
                                error="manual fixture exhausted",
                            )
                        payload_file = self._payloads[self._index]
                        self._index += 1
                        try:
                            content = payload_file.read_text(encoding="utf-8")
                        except OSError as exc:
                            return HarnessResult(
                                content="",
                                exit_code=1,
                                error=f"manual fixture unreadable: {exc}",
                            )
                        _, problems = validate_payload_text(
                            content,
                            expected_role=role_from_filename(payload_file.name),
                            source=payload_file.name,
                        )
                        if problems:
                            detail = "; ".join(problems)
                            return HarnessResult(
                                content="",
                                exit_code=1,
                                error=f"manual payload invalid: {detail}",
                            )
                        return HarnessResult(
                            content=content,
                            exit_code=0,
                            raw_response={"fixture": payload_file.name},
                        )
                    stream = cast(Any, click.get_text_stream)("stdin")
                    while True:
                        console.print(
                            f"[bold yellow][manual] Paste the '{role}' response; "
                            "end with EOF (Ctrl-D).[/bold yellow]"
                        )
                        console.print(prompt)
                        data = stream.read()
                        if not data.strip():
                            return HarnessResult(
                                content="", exit_code=1, error="empty manual response"
                            )
                        expected = role if role in MANUAL_ROLES else None
                        _, problems = validate_payload_text(
                            data, expected_role=expected, source="pasted payload"
                        )
                        if not problems:
                            return HarnessResult(content=data, exit_code=0)
                        console.print(
                            "[bold red][manual] payload rejected; fix and repaste:[/bold red]"
                        )
                        for problem in problems:
                            console.print(f"[red]  - {problem}[/red]")

            payload_dir = Path(fixture_env) if fixture_env else None
            if payload_dir is not None and not payload_dir.is_dir():
                raise click.UsageError(f"STC_MANUAL_FIXTURE_DIR is not a directory: {fixture_env}")
            backend = CLIGatewayBackend(
                "mock",
                project_root=source_root,
                ledger=ledger,
                harness=_ManualHarness(payload_dir),
                task_label="manual",
            )
            limitations.append("manual mode: operator/clipboard payloads, no live models")
        elif exec_harness is not None:
            from prompt_kit.harnesses.base import (
                HarnessResult,
            )

            from stc.integration.exec_harness import ExecHarness

            # Eager pin import: fail in seconds here, not minutes into the
            # run at the first execute() call (mirrors the manual branch).
            _ = HarnessResult
            exe_path = Path(exec_harness).expanduser()
            if not exe_path.is_absolute():
                raise click.UsageError(
                    f"--exec-harness must be an absolute path, got {exec_harness!r}."
                )
            if not exe_path.is_file():
                raise click.UsageError(f"--exec-harness is not a file: {exe_path}.")
            if not os.access(exe_path, os.X_OK):
                raise click.UsageError(f"--exec-harness is not executable: {exe_path}.")
            backend = CLIGatewayBackend(
                "mock",
                project_root=source_root,
                ledger=ledger,
                timeout=280.0,
                harness=ExecHarness(exe_path, timeout=280.0),
                task_label=f"exec:{exe_path.name}",
            )
            limitations.append(
                f"exec-harness mode: operator-authorized executable {exe_path} "
                "(explicit launch only, no live models)"
            )
        else:
            codex_home = _seed_codex_home()
            if codex_home is None:
                raise click.ClickException(
                    "Operator codex login unavailable (~/.codex/auth.json missing)."
                )
            backend = CLIGatewayBackend(
                "codex",
                project_root=source_root,
                ledger=ledger,
                timeout=280.0,
                harness_env={"CODEX_HOME": str(codex_home)},
            )
            limitations.append("single-harness run (codex; agy down per P05 B1.5)")

        gateway = CLIModelGateway(backend)
        from sst.gateway.contracts import ModelCatalog, ProviderKind, ProviderProfile

        gateway.register_profile(
            ProviderProfile(
                name="cli",
                kind=ProviderKind.TEST,
                api_base="cli://local",
                selected_model="default",
                # Controller requests carry no timeout, so the profile value
                # governs per-call latency; 60s default starves real codex
                # tasks (trial run: 2 diverge timeouts). Aligned with backend.
                timeout_seconds=280,
                catalog=ModelCatalog(),
            )
        )
        runner = DialecticRunner(
            ctx=ctx_obj,
            gateway=gateway,
            substrate=substrate,
            evidence_root=dossier_dir / "runs",
            memory=FileBackedMemory(),
            policy=policy,
            auditor=auditor,
            champion_mutmut=True,
        )
        if not json_mode:
            console.print(f"[bold green]Running dialectic loop: {active_task_id}[/bold green]")
        result = runner.run(bundle)
    finally:
        if codex_home is not None:
            try:
                sync_record = _sync_seeded_home_back(codex_home)
            except Exception as exc:  # sync must never fail the run
                sync_record = {"disposition": "sync-error", "error": str(exc)[:100]}
            logger.info("seeded codex home sync-back: %s", sync_record.get("disposition"))
            shutil.rmtree(codex_home, ignore_errors=True)

    ledger_path = dossier_dir / "spend_ledger.jsonl"
    spend_rows: list[dict[str, Any]] = []
    if ledger_path.is_file():
        for line in ledger_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                with contextlib.suppress(json.JSONDecodeError):
                    row = json.loads(line)
                    if isinstance(row, dict):
                        spend_rows.append(row)

    artifacts = assemble_dossier(
        result,
        dossier_dir,
        spec_id=atom.spec_id,
        task_id=active_task_id,
        contract_revision="INT-2026-09-13.2",
        base_identity=_dossier_base_identity(source_root, base_commit),
        qa=qa,
        spend_rows=spend_rows,
        limitations=limitations,
    )
    accepted, outcome_reason = final_outcome(result)
    if json_mode:
        click.echo(
            json.dumps(
                {
                    "status": "champion" if accepted else "no-champion",
                    "reason": outcome_reason,
                    "dossier_dir": str(dossier_dir),
                    "run_id": result.run_id,
                    "tree_id": result.tree_id,
                    "artifacts": artifacts,
                },
                indent=2,
            )
        )
    elif accepted:
        assert isinstance(result, ChampionResult)
        console.print(
            f"[bold green][+] Champion {result.champion_id} — dossier at {dossier_dir}[/bold green]"
        )
    else:
        console.print(
            f"[bold red][!] No champion ({outcome_reason}) — NEEDS_REPAIR "
            f"dossier at {dossier_dir}[/bold red]"
        )
    if not accepted:
        raise click.ClickException(f"No champion ({outcome_reason}) — dossier at {dossier_dir}.")


@main.command("run")
@click.argument("spec_path", type=click.Path(exists=True, path_type=Path))
@click.option("--pytest-target", default=None, help="Target test path for Pytest gate.")
@click.option("--task-id", default=None, help="Task identifier (defaults to spec stem).")
# Branch point (re-specified per section 5.3): explicit user input for an
# off-evaluation-path CLI op; the evaluation path never reads this.
@click.option("--base-branch", default="main", help="Base branch to fork leased worktree from.")
@click.option(
    "--yes", "-y", is_flag=True, default=False, help="Automatically accept Sovereign merge prompt."
)
@click.option(
    "--max-epochs", default=3, type=int, help="Maximum allowable retry epochs on circuit failure."
)
@click.option(
    "--with-codex",
    is_flag=True,
    default=False,
    help="Explicitly verify OpenAI Codex CLI execution runtime.",
)
@click.option(
    "--target",
    type=click.Choice(["dag", "stc"]),
    default="dag",
    show_default=True,
    help="Execution backend: existing DAG pipeline (default) or STC dialectic loop.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="With --target stc: print packets + budgets with zero model calls; exit 0.",
)
@click.option(
    "--manual",
    is_flag=True,
    default=False,
    help="With --target stc: drive the loop with manual payloads "
    "(STC_MANUAL_FIXTURE_DIR files, else operator stdin).",
)
@click.option(
    "--exec-harness",
    "exec_harness",
    default=None,
    metavar="PATH",
    help="With --target stc: drive the loop with an operator-authorized "
    "executable (absolute path). The exe receives each prompt on stdin "
    "with STC_HARNESS_ROLE set, and its stdout is the response. "
    "Runs with the operator's local agency; never unattended.",
)
@click.option(
    "--budget",
    default=None,
    help="With --target stc: k=v overrides, e.g. "
    "'time=600,tokens=500000,usd=10,iters=2,branching=1,depth=4'.",
)
@click.option(
    "--choice",
    type=click.Choice(["1", "2"]),
    default=None,
    help="With --target stc: pre-recorded operator choice for a >=tau dilemma.",
)
@click.pass_context
def run_cmd(
    ctx: click.Context,
    spec_path: Path,
    pytest_target: str | None,
    task_id: str | None,
    base_branch: str,
    yes: bool,
    max_epochs: int,
    with_codex: bool,
    target: str,
    dry_run: bool,
    manual: bool,
    exec_harness: str | None,
    budget: str | None,
    choice: str | None,
) -> None:
    """Execute the full end-to-end DAG from spec intake to promotion candidate."""
    if target != "stc" and (
        dry_run or manual or exec_harness is not None or budget is not None or choice is not None
    ):
        raise click.UsageError(
            "--dry-run/--manual/--exec-harness/--budget/--choice require --target stc."
        )
    if target == "stc":
        _run_stc_target(
            ctx,
            spec_path=spec_path,
            task_id=task_id,
            yes=yes,
            target=target,
            dry_run=dry_run,
            manual=manual,
            exec_harness=exec_harness,
            budget=budget,
            choice=choice,
            with_codex=with_codex,
            pytest_target=pytest_target,
            base_branch=base_branch,
            max_epochs=max_epochs,
        )
        return
    json_mode = ctx.obj.get("JSON_MODE", False)
    repo_root = Path.cwd()

    if not json_mode:
        console.print(
            Panel(f"[bold green]Starting Autonomous STC Pipeline for {spec_path}[/bold green]")
        )

    # Step 1: N01 & N02 Ingest & Validate Spec
    if not json_mode:
        console.print("1. [cyan]N01-N02: Ingest & Validate Spec Atom[/cyan] ... ", end="")
    atom = _load_and_validate_spec(spec_path)
    active_task_id = task_id or f"TASK-{atom.spec_id.upper()}"
    if not json_mode:
        console.print(f"[green]DONE[/green] (Spec ID: {atom.spec_id})")

    # Step 2: N03 Socratic Decomposition
    if not json_mode:
        console.print("2. [cyan]N03: Tree of Concerns (TOC) Decomposition[/cyan] ... ", end="")
    decomposer = SocraticDecomposer()
    toc = decomposer.decompose(atom)
    if not json_mode:
        console.print(f"[green]DONE[/green] (Ambiguity Score: {toc.ambiguity_score:.2f})")

    # Step 3: N04 - N06 Ambiguity Detection & Invariant Locking
    diffs = decomposer.detect_ambiguity(toc)
    if diffs:
        if not json_mode:
            console.print(
                f"   [bold yellow][!] High ambiguity ({toc.ambiguity_score:.2f} >= {TAU:.2f}). "
                "Resolving structured dilemma...[/bold yellow]"
            )
        selected_choices: list[int] = []
        for diff in diffs:
            if not json_mode and not yes:
                console.print(f"   [yellow]Dilemma:[/yellow] {diff.core_dilemma}")
                console.print(f"     (1) {diff.option_a.title}: {diff.option_a.tradeoff_pro}")
                console.print(f"     (2) {diff.option_b.title}: {diff.option_b.tradeoff_pro}")
                try:
                    choice = click.prompt(
                        "   Select choice [1/2]",
                        type=click.Choice(["1", "2"]),
                        default="1",
                        show_default=True,
                    )
                except click.Abort as exc:
                    raise click.ClickException(
                        "Sovereign choice aborted (timeout/abort) — routed to CIRCUIT_FAIL (N05)."
                    ) from exc
                selected_choices.append(int(choice))
            else:
                selected_choices.append(1)

        locked_path = decomposer.lock_invariants(toc, selected_choices)
        if not json_mode:
            console.print(f"   [green][+] Invariants locked to {locked_path}[/green]")

    # Step 4: N07 - N08 Hippocampal Memory & Inhibitor Fetch
    if not json_mode:
        console.print("3. [cyan]N07-N08: Query Hippocampal Trace Memory[/cyan] ... ", end="")
    trace_client = TraceClient()
    active_inhibitors: list[str] = []
    if trace_client.has_live_db:
        keywords = [atom.spec_id]
        if toc.domain_invariants and toc.domain_invariants.invariants:
            keywords.extend(toc.domain_invariants.invariants[0].split()[:3])
        trace_client.query_semantic_context(keywords)
        active_inhibitors.extend(trace_client.query_negative_inhibitors(active_task_id))
    if not json_mode:
        console.print(f"[green]DONE[/green] ({len(active_inhibitors)} inhibitors active)")

    # Bounded Epoch Retry Loop (N09 through N19)
    manager = WorktreeManager(repo_root=repo_root)
    runner = SubstrateRunner()
    auditor = JudiciaryAuditor(runner=runner, with_codex=with_codex)
    epoch_index = 1
    final_lease: WorktreeLease | None = None
    final_bundle: TaskBundle | None = None
    final_receipt: ExecutionReceipt | None = None
    final_verdict: JudiciaryVerdict | None = None
    final_diff: str = ""

    while epoch_index <= max_epochs:
        if not json_mode:
            console.print(
                f"\n[bold blue]─── Epoch {epoch_index}/{max_epochs} Execution ───[/bold blue]"
            )

        # N09: Context Compilation (Sub-25KB Task Bundle)
        if not json_mode:
            console.print("4. [cyan]N09: Context Compilation (Bundle <= 25KB)[/cyan] ... ", end="")
        bundle, byte_size, _yaml_str = _compile_bundle(
            atom,
            task_id=active_task_id,
            epoch_index=epoch_index,
            trace_memory=trace_client if trace_client.has_live_db else None,
            negative_inhibitors=active_inhibitors,
        )
        final_bundle = bundle
        if not json_mode:
            console.print(f"[green]DONE[/green] ({byte_size} bytes)")

        # N10: Leased Git Worktree Allocation
        if not json_mode:
            console.print("5. [cyan]N10: Allocate Leased Git Worktree[/cyan] ... ", end="")
        try:
            lease = manager.allocate_lease(
                task_id=active_task_id,
                base_branch=base_branch,
                epoch=epoch_index,
            )
        except WorktreeError as exc:
            raise click.ClickException(f"Failed to allocate worktree lease: {exc}") from exc
        final_lease = lease
        wt_path = Path(lease.worktree_path)
        if not json_mode:
            console.print(f"[green]DONE[/green] ({lease.branch_name} at {wt_path.name})")

        # N11: Verify Typing Membranes
        if not json_mode:
            console.print("6. [cyan]N11: Verify Typing Membranes[/cyan] ... ", end="")
        worker = CLIChaperoneWorker()
        if not worker.prove_membrane(lease):
            diagnostic = f"Membrane verification failed: upstream schemas missing in {wt_path}"
            active_inhibitors.append(diagnostic)
            epoch_index += 1
            if epoch_index > max_epochs:
                manager.quarantine_lease(active_task_id, reason=diagnostic)
                raise click.ClickException(
                    f"Pipeline halted: Membrane check failed across {max_epochs} epochs."
                )
            manager.release_lease(lease, purge=True)
            continue
        if not json_mode:
            console.print("[green]PASS[/green] (PEP 544 Protocols & Pydantic V2 verified)")

        # N12: Dispatch Executive Worker confined to worktree
        if not json_mode:
            console.print("7. [cyan]N12: Dispatch Executive Worker (Chaperone)[/cyan] ... ", end="")
        try:
            dispatch_worker(bundle, lease, worker)
        except WorktreeError as exc:
            diagnostic = f"Worker dispatch failed: {exc}"
            active_inhibitors.append(diagnostic)
            epoch_index += 1
            if epoch_index > max_epochs:
                manager.quarantine_lease(active_task_id, reason=diagnostic)
                raise click.ClickException(
                    f"Pipeline halted: Worker dispatch error across {max_epochs} epochs: {exc}"
                ) from exc
            manager.release_lease(lease, purge=True)
            continue
        if not json_mode:
            console.print("[green]DONE[/green] (Notary custody attested)")

        # N13 - N16: Substrate Hard Quality Gates
        if not json_mode:
            console.print("8. [cyan]N13-N16: Mechanical Substrate Gates[/cyan] ... ", end="")
        target_tests = pytest_target
        run_mutmut = True
        if "PYTEST_CURRENT_TEST" in os.environ:
            run_mutmut = False
            if target_tests is None:
                target_tests = "tests/unit/test_config.py"

        receipt = runner.execute_gates(
            worktree_path=wt_path,
            task_id=active_task_id,
            epoch_index=epoch_index,
            pytest_target=target_tests,
            run_mutmut=run_mutmut,
        )
        final_receipt = receipt

        if not receipt.is_passing:
            failing = [
                name
                for name, gate in [
                    ("ruff", receipt.gate_ruff),
                    ("mypy", receipt.gate_mypy),
                    ("pytest", receipt.gate_pytest),
                    ("mutmut", receipt.gate_mutmut),
                ]
                if gate.exit_code != 0
            ]
            diagnostic = f"Substrate gate failure at epoch {epoch_index}: {', '.join(failing)}"
            if not json_mode:
                console.print(f"[red]FAIL[/red] ({', '.join(failing)})")
            active_inhibitors.append(diagnostic)
            epoch_index += 1
            if epoch_index > max_epochs:
                manager.quarantine_lease(active_task_id, reason=diagnostic)
                raise click.ClickException(
                    f"Pipeline halted: Substrate gates failed across {max_epochs} epochs."
                )
            manager.release_lease(lease, purge=True)
            continue

        if not json_mode:
            console.print(f"[green]PASS[/green] (Receipt: {receipt.receipt_id})")

        # N17: Sign Machine Receipt (R1: no hardcoded dir; STC_RECEIPTS_DIR
        # override wins, else the in-tree default — CLI default unchanged).
        save_receipt(receipt)

        # N17J: Sync Barrier (Join)
        if not runner.verify_receipt(receipt):
            diagnostic = "Receipt HMAC-SHA256 signature verification failed at N17J join"
            active_inhibitors.append(diagnostic)
            epoch_index += 1
            if epoch_index > max_epochs:
                manager.quarantine_lease(active_task_id, reason=diagnostic)
                raise click.ClickException(
                    "Pipeline halted: Receipt signature failed at N17J join."
                )
            manager.release_lease(lease, purge=True)
            continue

        # N18: Blind Judiciary Red Team Audit
        if not json_mode:
            console.print("9. [cyan]N18-N19: Blind Judiciary Audit[/cyan] ... ", end="")
        diff_text = manager.get_diff(lease)
        final_diff = diff_text
        verdict = auditor.audit_diff(diff_text=diff_text, bundle=bundle, receipt=receipt)
        final_verdict = verdict

        # N19: Evaluate Verdict
        if verdict.status != "APPROVED":
            diagnostic = (
                f"Judiciary audit {verdict.status} at epoch {epoch_index}: "
                f"{verdict.summary_rationale}"
            )
            if not json_mode:
                console.print(f"[red]{verdict.status}[/red] ({verdict.summary_rationale})")
            active_inhibitors.append(diagnostic)
            epoch_index += 1
            if epoch_index > max_epochs:
                manager.quarantine_lease(active_task_id, reason=diagnostic)
                raise click.ClickException(
                    f"Pipeline halted: Judiciary audit {verdict.status} across {max_epochs} epochs."
                )
            manager.release_lease(lease, purge=True)
            continue

        if not json_mode:
            console.print("[green]APPROVED[/green] (0 violations)")
        break

    if (
        final_lease is None
        or final_bundle is None
        or final_receipt is None
        or final_verdict is None
    ):
        raise click.ClickException("Pipeline halted without generating execution candidate.")

    # In JSON mode: output pure JSON and clean up worktree
    if json_mode:
        manager.release_lease(final_lease, purge=True)
        payload = {
            "spec_atom": atom.model_dump(mode="json"),
            "tree_of_concerns": toc.model_dump(mode="json"),
            "task_bundle": final_bundle.model_dump(mode="json"),
            "worktree_lease": final_lease.model_dump(mode="json"),
            "execution_receipt": final_receipt.model_dump(mode="json"),
            "judiciary_verdict": final_verdict.model_dump(mode="json"),
        }
        click.echo(json.dumps(payload, indent=2))
        return

    # Tier 6: Promotion & Sovereign Merge (N20 - N22)
    console.print("\n[bold yellow][?] Sovereign Merge Authority Required.[/bold yellow]")
    console.print(f"  Task: {active_task_id}")
    console.print(f"  Receipt: {final_receipt.receipt_id} (VERIFIED)")
    console.print(f"  Judiciary: {final_verdict.status}")

    do_merge = yes
    if not do_merge:
        try:
            do_merge = click.confirm("Merge to main?", default=False)
        except click.Abort:
            do_merge = False

    if do_merge:
        # N20: Sovereign Promotion & Merge
        merge_res = subprocess.run(
            [
                "git",
                "merge",
                "--no-ff",
                "-m",
                f"Merge branch '{final_lease.branch_name}' ({active_task_id})",
                final_lease.branch_name,
            ],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
        if merge_res.returncode != 0:
            subprocess.run(
                ["git", "merge", "--abort"],
                cwd=repo_root,
                capture_output=True,
                check=False,
            )
            raise click.ClickException(
                f"Git merge failed (exit {merge_res.returncode}): "
                f"{merge_res.stderr or merge_res.stdout}. Promotion aborted."
            )

        console.print(
            f"[bold green][+] Merged branch {final_lease.branch_name} "
            f"to {base_branch}.[/bold green]"
        )

        # N21: Ingest into Trace Genome DB
        genome_store = GenomeStore()
        ingested_genes = genome_store.ingest_trace(
            task_id=active_task_id,
            receipt=final_receipt,
            diff_text=final_diff,
        )
        struct_count = sum(1 for g in ingested_genes if g.gene_type == GeneType.STRUCTURAL)
        behav_count = sum(1 for g in ingested_genes if g.gene_type == GeneType.BEHAVIORAL)
        console.print(
            f"[bold green][+] Ingested {struct_count} Structural Gene and "
            f"{behav_count} Behavioral Gene into Trace Genome DB.[/bold green]"
        )

        # N22: Worktree cleanup
        manager.release_lease(final_lease, purge=True)
        console.print(
            f"[bold green][+] Released worktree {final_lease.worktree_path}. "
            f"Task {active_task_id} COMPLETED.[/bold green]"
        )
    else:
        console.print(
            "[yellow][!] Sovereign declined merge. Leased worktree preserved at "
            f"{final_lease.worktree_path}.[/yellow]"
        )


if __name__ == "__main__":
    main()
