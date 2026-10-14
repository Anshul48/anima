"""Deterministic Socratic specification decomposer producing a 5-dimensional Tree of Concerns."""

from __future__ import annotations

import hashlib
import os
import re
from datetime import UTC, datetime
from pathlib import Path

from stc.protocols.interfaces import SocraticDecomposerProtocol
from stc.schemas.models import (
    ArchetypeDiff,
    ConcernDimension,
    SpecAtom,
    TreeOfConcerns,
)
from stc.socratic.ambiguity import (
    TAU,
    compute_ambiguity_score,
    generate_archetype_diff,
    generate_archetype_diffs,
)

DIMENSION_HEADER_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "domain_invariants",
        re.compile(
            r"\b(invariant|invariants|domain|rules?|business\s+rules?|guarantees?)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "persistence_storage",
        re.compile(
            r"\b(storage|persistence|persist|database|sqlite|schemas?|tables?|stores?)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "communication_protocols",
        re.compile(
            r"\b(protocols?|communication|interfaces?|transports?|apis?|endpoints?|messages?|channels?)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "boundary_security",
        re.compile(
            r"\b(security|boundary|boundaries|sandboxes?|sandboxing|isolation|auth|authentication|authorization|permissions?|pii|tokens?)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "failure_resilience",
        re.compile(
            r"\b(resilience|failures?|faults?|errors?|recovery|timeouts?|retries|retry|circuits?|fallbacks?|backoff)\b",
            re.IGNORECASE,
        ),
    ),
]


def _clean_line(line: str) -> str:
    """Strip markdown bullet markers, HTML comments/tags, numbers, and extra whitespace."""
    stripped = line.strip()
    # Strip HTML comments: <!-- ... -->
    stripped = re.sub(r"<!--.*?-->", "", stripped, flags=re.DOTALL).strip()
    if not stripped:
        return ""
    # Strip basic HTML tags
    stripped = re.sub(r"</?[a-zA-Z][^>]*>", "", stripped).strip()
    # Remove leading list markers: "- ", "* ", "1. ", "• "
    stripped = re.sub(r"^[-*•]\s+", "", stripped)
    stripped = re.sub(r"^\d+\.\s+", "", stripped)
    return stripped.strip()


def _classify_section_header(header: str) -> str | None:
    """Map markdown header text to one of the 5 concern dimensions using word boundaries."""
    h_clean = header.strip()
    # Explicit check for author metadata header to avoid false boundary_security match
    if re.search(r"^\s*author\b", h_clean, re.IGNORECASE):
        return None

    for dim_name, pattern in DIMENSION_HEADER_PATTERNS:
        if pattern.search(h_clean):
            return dim_name
    return None


class SocraticDecomposer:
    """Socratic specification elicitation engine conforming to SocraticDecomposerProtocol."""

    def decompose(self, spec: SpecAtom) -> TreeOfConcerns:
        """Decompose specification text into a 5-dimensional Tree of Concerns (TOC)."""
        content = spec.raw_content.replace("\r\n", "\n").replace("\r", "\n")
        lines = content.splitlines()

        # Section-based buckets
        buckets: dict[str, list[str]] = {
            "domain_invariants": [],
            "persistence_storage": [],
            "communication_protocols": [],
            "boundary_security": [],
            "failure_resilience": [],
        }

        current_dimension: str | None = None

        for line in lines:
            line_str = line.strip()
            if not line_str:
                continue

            # Check markdown heading
            if line_str.startswith("#"):
                raw_hashes = len(line_str) - len(line_str.lstrip("#"))
                header_text = line_str.lstrip("#").strip()

                if raw_hashes == 1:
                    # Top-level H1 document title
                    is_explicit_dim = any(
                        phrase in header_text.lower()
                        for phrase in [
                            "domain invariants",
                            "persistence & storage",
                            "communication protocols",
                            "boundary & security",
                            "failure resilience",
                        ]
                    )
                    current_dimension = (
                        _classify_section_header(header_text) if is_explicit_dim else None
                    )
                    continue

                detected = _classify_section_header(header_text)
                if raw_hashes == 2:
                    current_dimension = detected
                else:
                    # Subsections (###, ####): switch if detected; else retain current dimension
                    if detected is not None:
                        current_dimension = detected
                continue

            cleaned = _clean_line(line_str)
            if not cleaned:
                continue

            if current_dimension:
                buckets[current_dimension].append(cleaned)
            else:
                # Classify loose statements by keywords if outside a recognized header
                loose_dim = _classify_section_header(cleaned)
                if loose_dim:
                    buckets[loose_dim].append(cleaned)

        # Build ConcernDimensions
        dim_inv = ConcernDimension(
            dimension_name="domain_invariants",
            invariants=[item for item in buckets["domain_invariants"] if item],
        )
        dim_pers = ConcernDimension(
            dimension_name="persistence_storage",
            contracts=[item for item in buckets["persistence_storage"] if item],
        )
        dim_comm = ConcernDimension(
            dimension_name="communication_protocols",
            contracts=[item for item in buckets["communication_protocols"] if item],
        )
        dim_sec = ConcernDimension(
            dimension_name="boundary_security",
            contracts=[item for item in buckets["boundary_security"] if item],
        )
        dim_res = ConcernDimension(
            dimension_name="failure_resilience",
            failure_modes=[item for item in buckets["failure_resilience"] if item],
        )

        draft_toc = TreeOfConcerns(
            spec_id=spec.spec_id,
            domain_invariants=dim_inv,
            persistence_storage=dim_pers,
            communication_protocols=dim_comm,
            boundary_security=dim_sec,
            failure_resilience=dim_res,
            ambiguity_score=0.0,
        )

        score = compute_ambiguity_score(draft_toc, raw_text=content)

        return TreeOfConcerns(
            spec_id=spec.spec_id,
            domain_invariants=dim_inv,
            persistence_storage=dim_pers,
            communication_protocols=dim_comm,
            boundary_security=dim_sec,
            failure_resilience=dim_res,
            ambiguity_score=score,
        )

    def detect_ambiguity(
        self,
        toc: TreeOfConcerns,
        raw_text: str = "",
    ) -> list[ArchetypeDiff]:
        """Detect architectural ambiguities and emit pairwise ArchetypeDiff on tau trigger."""
        if toc.ambiguity_score >= TAU:
            return generate_archetype_diffs(toc, raw_text=raw_text)
        return []

    def lock_invariants(
        self,
        toc: TreeOfConcerns,
        selected_archetypes: list[int],
        output_path: Path | None = None,
    ) -> Path:
        """Lock selected archetype opinions into immutable invariant specifications."""
        diffs = self.detect_ambiguity(toc)
        if not diffs:
            diffs = [generate_archetype_diff(toc)]

        chosen_options = []
        for i, diff in enumerate(diffs):
            selection = selected_archetypes[i] if i < len(selected_archetypes) else 1
            chosen = diff.option_b if selection == 2 else diff.option_a
            chosen_options.append(chosen)

        if output_path is None:
            out_dir = Path(os.environ.get("STC_INVARIANTS_DIR", "specs/invariants"))
            out_dir.mkdir(parents=True, exist_ok=True)
            output_path = out_dir / f"{toc.spec_id.upper()}_INVARIANTS.md"
        else:
            output_path.parent.mkdir(parents=True, exist_ok=True)

        primary_title = chosen_options[0].title if chosen_options else "Archetype Alpha"

        lines: list[str] = [
            f"# Locked Invariants: {toc.spec_id}",
            "> Generated by STC Socratic Decomposition Engine",
            f"> Timestamp: {datetime.now(UTC).isoformat()}",
            f"> Ambiguity Score: {toc.ambiguity_score:.2f}",
            f"> Selected Archetype: {primary_title}",
            "",
            "## Active Domain Invariants",
        ]

        for inv in toc.domain_invariants.invariants:
            lines.append(f"- {inv}")
        if not toc.domain_invariants.invariants:
            lines.append("- None extracted from specification")

        lines.append("")
        lines.append("## Locked Archetype Decisions")
        for diff, chosen_option in zip(diffs, chosen_options, strict=False):
            lines.extend(
                [
                    f"### Dilemma: {diff.core_dilemma}",
                    f"**Chosen Option:** {chosen_option.title}",
                    f"**Trade-off Pro:** {chosen_option.tradeoff_pro}",
                    f"**Trade-off Con:** {chosen_option.tradeoff_con}",
                    "",
                    "### Prescribed Invariants",
                ]
            )
            for inv_lock in chosen_option.invariants_to_lock:
                lines.append(f"- [INVARIANT] {inv_lock}")
            lines.append("")

        content = "\n".join(lines).rstrip() + "\n"
        sha256 = hashlib.sha256(content.encode("utf-8")).hexdigest()
        final_content = f"{content}\n---\n**SHA-256 Checksum:** `{sha256}`\n"

        output_path.write_text(final_content, encoding="utf-8")
        return output_path


# Ensure runtime protocol compliance
def _assert_protocol_compliance() -> None:
    _instance: SocraticDecomposerProtocol = SocraticDecomposer()


__all__ = [
    "SocraticDecomposer",
]
