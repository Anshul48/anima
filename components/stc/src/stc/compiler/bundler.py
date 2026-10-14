"""Module: stc.compiler.bundler
Context Compiler & Task Bundle Assembler enforcing the strict 25KB ceiling.
"""

from __future__ import annotations

import re
import time
import uuid
from pathlib import Path

import yaml

from stc.core.errors import BundleSizeExceededError
from stc.protocols.interfaces import ContextCompilerProtocol, TraceMemoryProtocol
from stc.schemas.models import FileTarget, SpecAtom, TaskBundle, TreeOfConcerns

MAX_BUNDLE_BYTES: int = 25600


class ContextCompiler(ContextCompilerProtocol):
    """Compiles atomic sub-25KB TaskBundle execution packages with hierarchical pruning."""

    def __init__(
        self,
        trace_memory: TraceMemoryProtocol | None = None,
        max_bundle_bytes: int = MAX_BUNDLE_BYTES,
    ) -> None:
        self.trace_memory = trace_memory
        self.max_bundle_bytes = max_bundle_bytes
        self.last_pruned_traces_count: int = 0
        self.last_pruned_inhibitors_count: int = 0
        self.initial_bundle_bytes: int = 0
        self.last_bundle_bytes: int = 0
        self.hippocampal_coverage: bool = False
        self.hippocampal_query_latency_ms: float = 0.0

    @staticmethod
    def _extract_keywords(spec_id: str, goal: str, toc: TreeOfConcerns) -> list[str]:
        """Extract meaningful keywords for semantic retrieval across all TOC dimensions."""
        raw_terms: list[str] = []
        raw_terms.extend(spec_id.replace("-", "_").split("_"))
        raw_terms.extend(re.findall(r"\b[a-zA-Z]{3,}\b", goal.lower()))
        for inv in toc.domain_invariants.invariants:
            raw_terms.extend(re.findall(r"\b[a-zA-Z]{3,}\b", inv.lower()))
        for contract in toc.persistence_storage.contracts:
            raw_terms.extend(re.findall(r"\b[a-zA-Z]{3,}\b", contract.lower()))
        for proto in toc.communication_protocols.contracts:
            raw_terms.extend(re.findall(r"\b[a-zA-Z]{3,}\b", proto.lower()))
        for sec in toc.boundary_security.contracts:
            raw_terms.extend(re.findall(r"\b[a-zA-Z]{3,}\b", sec.lower()))
        for fail in toc.failure_resilience.failure_modes:
            raw_terms.extend(re.findall(r"\b[a-zA-Z]{3,}\b", fail.lower()))

        stopwords = {
            "the",
            "and",
            "for",
            "with",
            "that",
            "this",
            "from",
            "are",
            "was",
            "were",
            "will",
            "must",
            "never",
            "should",
            "could",
            "have",
            "has",
            "had",
            "not",
            "but",
            "into",
            "over",
            "after",
            "spec",
            "test",
            "feature",
        }
        filtered = [t for t in raw_terms if t not in stopwords and len(t) >= 3]
        # Deduplicate preserving order
        seen: set[str] = set()
        unique: list[str] = []
        for term in filtered:
            if term not in seen:
                seen.add(term)
                unique.append(term)
        return unique[:10]

    @staticmethod
    def _extract_spec_metadata(
        raw_content: str,
        spec_id: str = "",
        toc: TreeOfConcerns | None = None,
    ) -> tuple[list[FileTarget], list[str], list[str], list[str]]:
        """Extract candidate target files, membrane protocols, invariants, and inhibitors."""
        files: list[FileTarget] = []
        seen_files: set[str] = set()
        # Find explicit python paths quoted or unquoted
        for fp in re.findall(
            r"(?:[`'\"]|\b)((?:src/stc/|code/|tests/|[a-zA-Z0-9_\-/\\]+)[a-zA-Z0-9_\-/\\]*\.py)(?:[`'\"]|\b)",
            raw_content,
        ):
            normalized = fp.replace("\\", "/").lstrip("./")
            if normalized not in seen_files:
                seen_files.add(normalized)
                files.append(FileTarget(path=normalized, action="modify"))

        proto_matches = re.findall(r"\b([A-Z][a-zA-Z0-9]+Protocol)\b", raw_content)
        if toc:
            for contract in toc.communication_protocols.contracts:
                proto_matches.extend(re.findall(r"\b([A-Z][a-zA-Z0-9]+Protocol)\b", contract))
        protocols = sorted(set(proto_matches))

        invariants: list[str] = []
        inhibitors: list[str] = []
        for line in raw_content.splitlines():
            line_clean = line.strip().lstrip("#*- ").strip()
            if (
                any(k in line.lower() for k in ["must", "never", "invariant", "rule"])
                and len(line_clean) > 5
            ):
                invariants.append(line_clean[:100])
            if (
                any(k in line.lower() for k in ["inhibitor", "refuted", "avoid", "do not"])
                and len(line_clean) > 5
            ):
                inhibitors.append(line_clean[:100])

        return files, protocols, invariants, inhibitors

    def compile_task(
        self,
        task_id: str,
        spec: SpecAtom,
        toc: TreeOfConcerns,
        inhibitors: list[str],
        epoch_index: int = 1,
        target_files: list[FileTarget] | None = None,
        membrane_protocols: list[str] | None = None,
        correlation_id: str | None = None,
        causation_id: str | None = None,
    ) -> TaskBundle:
        """Assemble an atomic TaskBundle and enforce the 25KB ceiling via hierarchical pruning."""
        bundle, _byte_size, _yaml_str = self.compile_bundle(
            task_id=task_id,
            spec=spec,
            toc=toc,
            inhibitors=inhibitors,
            epoch_index=epoch_index,
            target_files=target_files,
            membrane_protocols=membrane_protocols,
            correlation_id=correlation_id,
            causation_id=causation_id,
        )
        return bundle

    def compile_bundle(
        self,
        task_id: str,
        spec: SpecAtom,
        toc: TreeOfConcerns,
        inhibitors: list[str],
        epoch_index: int = 1,
        target_files: list[FileTarget] | None = None,
        membrane_protocols: list[str] | None = None,
        correlation_id: str | None = None,
        causation_id: str | None = None,
    ) -> tuple[TaskBundle, int, str]:
        """Compile a TaskBundle and return (bundle, byte_size, yaml_str).

        Hierarchical context pruning is applied if size exceeds ceiling.
        """
        self.last_pruned_traces_count = 0
        self.last_pruned_inhibitors_count = 0

        # 1. Goal statement
        goal_statement = f"Execute specification requirements for {spec.spec_id}"
        for line in spec.raw_content.splitlines():
            line_str = line.strip()
            if line_str.startswith("#"):
                heading = line_str.lstrip("#").strip()
                if heading:
                    goal_statement = heading
                    break

        spec_files, spec_protos, spec_invs, spec_inhibitors = self._extract_spec_metadata(
            spec.raw_content,
            spec_id=spec.spec_id,
            toc=toc,
        )

        # 2. Neocortex Invariants (Protected from pruning)
        neocortex_invariants: list[str] = list(toc.domain_invariants.invariants)
        for inv in spec_invs:
            if inv not in neocortex_invariants:
                neocortex_invariants.append(inv)
        if not neocortex_invariants:
            neocortex_invariants = [
                "Zero mock certification policy",
                "Deterministic exit code 0 required",
                "Cross-OS execution neutrality",
            ]

        # 3. Target files & Membrane protocols (Inferred cleanly without unrelated hardcoding)
        inferred_fallback_path = f"src/stc/{spec.spec_id.replace('-', '_')}.py"
        resolved_files = target_files or (
            spec_files[:5]
            if spec_files
            else [
                FileTarget(
                    path=inferred_fallback_path,
                    action="modify",
                    expected_symbols=[],
                )
            ]
        )
        resolved_protocols = membrane_protocols or (
            spec_protos[:5] if spec_protos else ["SubstrateRunnerProtocol", "HormoneBusProtocol"]
        )

        # 4. Episodic traces & Negative inhibitors from Hippocampus
        episodic_traces: list[str] = []
        queried_inhibitors: list[str] = []
        self.hippocampal_coverage = False
        self.hippocampal_query_latency_ms = 0.0

        if self.trace_memory is not None:
            keywords = self._extract_keywords(spec.spec_id, goal_statement, toc)
            t_start = time.perf_counter()
            episodic_traces = self.trace_memory.query_semantic_context(keywords, max_results=3)
            self.hippocampal_query_latency_ms = (time.perf_counter() - t_start) * 1000.0

            # Query inhibitors for spec tokens, goal tokens, keywords, and general wildcard
            candidate_comps = [spec.spec_id.split("_")[0]]
            candidate_comps.extend(re.findall(r"\b[a-zA-Z]{3,}\b", goal_statement.lower()))
            candidate_comps.extend(keywords)

            for comp in candidate_comps:
                for inh in self.trace_memory.query_negative_inhibitors(comp):
                    if inh not in queried_inhibitors:
                        queried_inhibitors.append(inh)

            for inh in self.trace_memory.query_negative_inhibitors("*"):
                if inh not in queried_inhibitors:
                    queried_inhibitors.append(inh)

            if episodic_traces or queried_inhibitors:
                self.hippocampal_coverage = True

        # 5. Combined Negative Inhibitors
        combined_inhibitors: list[str] = []
        for inh in list(inhibitors) + queried_inhibitors + spec_inhibitors:
            clean_inh = inh.strip()
            if clean_inh and clean_inh not in combined_inhibitors:
                combined_inhibitors.append(clean_inh)
        if not combined_inhibitors:
            combined_inhibitors = [
                "Do not use mock assertions in verification tests",
                "Do not run native mutmut on Windows without WSL",
            ]

        # 6. Initial Candidate Assembly
        current_traces = list(episodic_traces)
        current_inhibitors = list(combined_inhibitors)

        def _build_and_measure(
            traces: list[str],
            inhs: list[str],
        ) -> tuple[TaskBundle, int, str]:
            invariants_payload = list(neocortex_invariants)
            for trace_str in traces:
                invariants_payload.append(f"[Trace] {trace_str}")

            b = TaskBundle(
                task_id=task_id,
                epoch_index=epoch_index,
                spec_id=spec.spec_id,
                goal_statement=goal_statement,
                invariants=invariants_payload,
                target_files=resolved_files,
                membrane_protocols=resolved_protocols,
                negative_inhibitors=inhs,
                correlation_id=correlation_id or f"corr_{uuid.uuid4().hex[:12]}",
                causation_id=causation_id,
            )
            serialized = yaml.safe_dump(b.model_dump(mode="json"), sort_keys=False)
            size = len(serialized.encode("utf-8"))
            return b, size, serialized

        bundle, byte_size, yaml_str = _build_and_measure(current_traces, current_inhibitors)
        self.initial_bundle_bytes = byte_size

        # 7. Hierarchical Context Pruning
        if byte_size > self.max_bundle_bytes:
            # Stage A: Prune low-ranking episodic traces one by one
            while byte_size > self.max_bundle_bytes and current_traces:
                current_traces.pop()
                self.last_pruned_traces_count += 1
                bundle, byte_size, yaml_str = _build_and_measure(current_traces, current_inhibitors)

            # Stage B: If still over ceiling, prune negative inhibitors one by one from the end
            while byte_size > self.max_bundle_bytes and current_inhibitors:
                current_inhibitors.pop()
                self.last_pruned_inhibitors_count += 1
                bundle, byte_size, yaml_str = _build_and_measure(current_traces, current_inhibitors)

            # Stage C: If still over ceiling, fail-closed per 01_INVARIANTS.md
            # Neocortex invariants are protected and cannot be dropped
            if byte_size > self.max_bundle_bytes:
                raise BundleSizeExceededError(
                    f"Context budget violated: task bundle size ({byte_size} bytes) exceeds "
                    f"{self.max_bundle_bytes} byte ceiling after hierarchical context pruning."
                )

        self.last_bundle_bytes = byte_size
        return bundle, byte_size, yaml_str

    @staticmethod
    def to_yaml(bundle: TaskBundle) -> str:
        """Serialize a TaskBundle to canonical YAML format."""
        dumped: str = yaml.safe_dump(bundle.model_dump(mode="json"), sort_keys=False)
        return dumped

    def save_bundle(self, bundle: TaskBundle, out_path: Path) -> Path:
        """Save a TaskBundle to disk as YAML."""
        out_path.parent.mkdir(parents=True, exist_ok=True)
        yaml_content = self.to_yaml(bundle)
        out_path.write_text(yaml_content, encoding="utf-8")
        return out_path


__all__ = ["MAX_BUNDLE_BYTES", "ContextCompiler"]
