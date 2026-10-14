"""Abstract PEP 544 interfaces for the Biomimetic Spec-to-Code Engine."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from stc.schemas.hormones import HormoneEvent
from stc.schemas.models import (
    ArchetypeDiff,
    ExecutionReceipt,
    GenomeAtom,
    JudiciaryVerdict,
    SpecAtom,
    TaskBundle,
    TreeOfConcerns,
    WorktreeLease,
)


@runtime_checkable
class SpecIngestorProtocol(Protocol):
    """Protocol for reading and sanitizing raw specifications."""

    def ingest_path(self, path: Path) -> SpecAtom: ...
    def ingest_string(self, content: str, source_name: str) -> SpecAtom: ...


@runtime_checkable
class SocraticDecomposerProtocol(Protocol):
    """Protocol for decomposing specifications into a Tree of Concerns (TOC)."""

    def decompose(self, spec: SpecAtom) -> TreeOfConcerns: ...
    def detect_ambiguity(self, toc: TreeOfConcerns, raw_text: str = "") -> list[ArchetypeDiff]: ...
    def lock_invariants(
        self,
        toc: TreeOfConcerns,
        selected_archetypes: list[int],
        output_path: Path | None = None,
    ) -> Path: ...


@runtime_checkable
class TraceMemoryProtocol(Protocol):
    """Protocol for querying the Project Trace cognitive memory store."""

    def query_semantic_context(self, keywords: list[str], max_results: int = 3) -> list[str]: ...
    def query_negative_inhibitors(self, component: str) -> list[str]: ...


@runtime_checkable
class ContextCompilerProtocol(Protocol):
    """Protocol for assembling sub-25KB task bundles."""

    def compile_task(
        self,
        task_id: str,
        spec: SpecAtom,
        toc: TreeOfConcerns,
        inhibitors: list[str],
    ) -> TaskBundle: ...


@runtime_checkable
class WorktreeManagerProtocol(Protocol):
    """Protocol for isolated Git worktree management."""

    # Branch point (re-specified per section 5.3): the default below is for
    # explicit off-evaluation-path callers only; the evaluation path passes
    # explicit scratch SHAs and never triggers it (see WorktreeManager).
    def allocate_lease(self, task_id: str, base_branch: str = "main") -> WorktreeLease: ...
    def release_lease(self, lease: WorktreeLease, purge: bool = True) -> None: ...
    def get_diff(self, lease: WorktreeLease) -> str: ...


@runtime_checkable
class WorkerProtocol(Protocol):
    """Protocol for executive workers (`agy` / `aider` / `dsh`) confined to a leased worktree."""

    def dispatch(self, bundle: TaskBundle, lease: WorktreeLease) -> str: ...
    def confinement_root(self, lease: WorktreeLease) -> Path: ...


@runtime_checkable
class SubstrateRunnerProtocol(Protocol):
    """Protocol for running deterministic quality gates and generating receipts.

    OS/mutmut execution policy (`run_mutmut`, Windows defer-to-WSL) is runner
    configuration owned by `stc.substrate` + `stc.core.config` — never membrane
    surface. The membrane carries only identity, targeting, and correlation.
    """

    def execute_gates(
        self,
        worktree_path: Path,
        task_id: str,
        epoch_index: int = 1,
        correlation_id: str | None = None,
        causation_id: str | None = None,
        pytest_target: str | None = None,
        paths_to_mutate: list[str] | None = None,
    ) -> ExecutionReceipt: ...

    def verify_receipt(self, receipt: ExecutionReceipt) -> bool: ...


@runtime_checkable
class JudiciaryAuditorProtocol(Protocol):
    """Protocol for blind adversarial inspection of diffs."""

    def audit_diff(
        self,
        diff_text: str,
        bundle: TaskBundle,
        receipt: ExecutionReceipt,
    ) -> JudiciaryVerdict: ...


@runtime_checkable
class GenomeStoreProtocol(Protocol):
    """Protocol for saving verified implementations and negative knowledge."""

    def save_gene(self, gene: GenomeAtom) -> str: ...
    def find_genes(self, tags: list[str]) -> list[GenomeAtom]: ...


@runtime_checkable
class HormoneBusProtocol(Protocol):
    """Protocol for scoped pub/sub cellular hormone message bus."""

    def publish(self, event: HormoneEvent) -> str:
        """Publish a typed hormone event to its scoped target channel."""
        ...

    def subscribe(
        self,
        subsystem_id: str,
        topics: list[str] | None = None,
    ) -> None:
        """Register a subsystem receptor on specific topics."""
        ...

    def poll_events(
        self,
        subsystem_id: str,
        max_events: int = 10,
    ) -> list[HormoneEvent]:
        """Retrieve pending scoped events addressed to this subsystem."""
        ...


__all__ = [
    "ContextCompilerProtocol",
    "GenomeStoreProtocol",
    "HormoneBusProtocol",
    "JudiciaryAuditorProtocol",
    "SocraticDecomposerProtocol",
    "SpecIngestorProtocol",
    "SubstrateRunnerProtocol",
    "TraceMemoryProtocol",
    "WorkerProtocol",
    "WorktreeManagerProtocol",
]
