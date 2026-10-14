"""Compilation of bounded AuDHD Context Capsules using Quad-Channel retrieval and repository indexing."""

from __future__ import annotations

import ast
import logging
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from sst.context.memory_adapter import NullMemoryProvider, wrap_trace_lite_db
from sst.core.models import AuDHDContextCapsule
from sst.protocols.memory import MemoryProviderProtocol, ProviderAvailability, ProviderStatus

logger = logging.getLogger(__name__)


class CapsuleCompileReport(BaseModel):
    """Provenance and availability record for one capsule compilation."""

    model_config = ConfigDict(frozen=True)

    provider_name: str
    adapter_version: str
    status: ProviderStatus
    insight_count: int = 0
    interface_count: int = 0
    evidence_refs: list[str] = Field(default_factory=list)
    provenance: list[str] = Field(default_factory=list)
    last_error: str | None = None


def memory_tree_payload_fragment(report: CapsuleCompileReport | None) -> dict[str, Any]:
    """Returns the TREE_CREATED payload fragment carrying memory provenance.

    B1 merges this fragment into the ``TREE_CREATED`` payload in
    ``sst/search/controller.py`` (see the B1 cross-requests); keys are
    stable and additive.
    """
    if report is None:
        return {}
    return {
        "memory_provider": report.provider_name,
        "memory_availability": report.status.value,
        "memory_adapter_version": report.adapter_version,
        "memory_evidence_refs": list(report.evidence_refs),
        "memory_insight_provenance": list(report.provenance),
        "memory_insight_count": report.insight_count,
        "memory_last_error": report.last_error,
    }


class ContextCapsuleCompiler:
    """Compiles concise, high-signal context capsules for SST nodes."""

    def __init__(
        self,
        workspace_root: Path | str,
        trace_lite_db: Any | None = None,
        memory_provider: MemoryProviderProtocol | None = None,
    ) -> None:
        self.workspace_root = Path(workspace_root)
        self.trace_lite_db = trace_lite_db
        if memory_provider is not None:
            self.memory_provider: MemoryProviderProtocol = memory_provider
        elif trace_lite_db is not None:
            self.memory_provider = wrap_trace_lite_db(trace_lite_db)
        else:
            self.memory_provider = NullMemoryProvider()
        self.last_report: CapsuleCompileReport | None = None

    def compile(
        self,
        goal: str,
        target_files: list[str] | None = None,
        invariants: list[str] | None = None,
        interfaces: list[str] | None = None,
        action_boundary: str | None = None,
        negative_constraints: list[str] | None = None,
        max_file_bytes: int = 15000,
        memory_limit: int = 5,
    ) -> AuDHDContextCapsule:
        """Assembles a bounded context capsule."""
        relevant_files: dict[str, str] = {}
        extracted_interfaces: list[str] = list(interfaces or [])

        if target_files:
            for rel_path in target_files:
                full_path = self.workspace_root / rel_path
                if full_path.exists() and full_path.is_file():
                    try:
                        content = full_path.read_text(encoding="utf-8", errors="replace")
                        # Extract AST interfaces if python
                        if rel_path.endswith(".py"):
                            ast_ifaces = self._extract_ast_interfaces(content, rel_path)
                            extracted_interfaces.extend(ast_ifaces)

                        if len(content) > max_file_bytes:
                            content = content[:max_file_bytes] + "\n... [TRUNCATED FOR CONTEXT CAPSULE] ..."
                        relevant_files[rel_path] = content
                    except Exception:
                        pass

        # Query the versioned memory provider for prior insights. Memory is an
        # optional accelerator: provider faults degrade the capsule (and are
        # surfaced via the compile report), they never fail compilation.
        literature_or_prior_insights: list[str] = []
        provenance: list[str] = []
        interface_count = 0
        try:
            provider_result = self.memory_provider.query_insights(goal, limit=memory_limit)
            availability = provider_result.availability
            for item in provider_result.insights:
                provenance.append(f"{item.layer}:{item.path or item.evidence_ref}")
                if item.kind == "interface":
                    if item.text not in extracted_interfaces:
                        extracted_interfaces.append(item.text)
                        interface_count += 1
                else:
                    literature_or_prior_insights.append(item.text)
        except Exception as exc:
            availability = ProviderAvailability(
                provider_name=self.memory_provider.provider_name,
                status=ProviderStatus.UNAVAILABLE,
                last_error=f"memory provider raised: {exc}",
            )

        if availability.last_error:
            logger.warning(
                "Memory provider '%s' reported error: %s",
                availability.provider_name,
                availability.last_error,
            )

        if availability.provider_name != "none":
            literature_or_prior_insights.append(
                f"[memory-provider:{availability.provider_name} status={availability.status.value} "
                f"adapter={availability.adapter_version} insights={availability.insight_count}]"
            )

        self.last_report = CapsuleCompileReport(
            provider_name=availability.provider_name,
            adapter_version=availability.adapter_version,
            status=availability.status,
            insight_count=availability.insight_count,
            interface_count=interface_count,
            evidence_refs=list(availability.evidence_refs),
            provenance=provenance,
            last_error=availability.last_error,
        )

        boundary = action_boundary or (
            f"You may only propose modifications to target files: {target_files or 'specified modules'}. "
            "Do not introduce new external third-party dependencies without explicit interface declaration."
        )

        report = self.last_report
        return AuDHDContextCapsule(
            goal=goal,
            memory_provider=report.provider_name if report else "none",
            memory_availability=report.status.value if report else "UNAVAILABLE",
            memory_evidence_refs=list(report.evidence_refs) if report else [],
            invariants=invariants
            or [
                "Preserve all existing public interface signatures and type contracts.",
                "Ensure all unit tests pass with zero regression.",
                "Keep code deterministic, modular, and thread-safe.",
            ],
            interfaces=extracted_interfaces,
            relevant_files=relevant_files,
            literature_or_prior_insights=literature_or_prior_insights,
            action_space_boundary=boundary,
            negative_constraints=negative_constraints
            or [
                "No hardcoded API keys or secrets.",
                "No unbounded recursive loops or uncontrolled allocations.",
            ],
        )

    def describe_memory(self) -> str:
        """Returns a one-line human summary of the wired memory provider."""
        report = self.last_report
        if report is not None:
            detail = f"insights={report.insight_count}"
            if report.last_error:
                detail += f" last_error={report.last_error}"
            return f"Memory provider: {report.provider_name} (status={report.status.value} {detail})"
        availability = self.memory_provider.check_availability()
        if availability.provider_name == "none":
            return "Memory provider: none (status=UNAVAILABLE — proceeding without prior insights)"
        detail = f"adapter={availability.adapter_version}"
        if availability.last_error:
            detail += f" last_error={availability.last_error}"
        return f"Memory provider: {availability.provider_name} (status={availability.status.value} {detail})"

    def _extract_ast_interfaces(self, source_code: str, file_path: str) -> list[str]:
        """Extracts class and function signature definitions for interface adherence."""
        interfaces: list[str] = []
        try:
            tree = ast.parse(source_code)
            for node in ast.iter_child_nodes(tree):
                if isinstance(node, ast.ClassDef):
                    methods = [
                        f"{'async def' if isinstance(n, ast.AsyncFunctionDef) else 'def'} {n.name}({', '.join(a.arg for a in n.args.args)})"
                        for n in node.body
                        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                    ]
                    interfaces.append(f"class {node.name}(methods: {', '.join(methods)}) in {file_path}")
                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
                    args = [a.arg for a in node.args.args]
                    interfaces.append(f"{prefix} {node.name}({', '.join(args)}) in {file_path}")
        except Exception:
            pass
        return interfaces
