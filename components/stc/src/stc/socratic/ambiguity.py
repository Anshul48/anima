"""Deterministic ambiguity detection and archetype diff generation for STC Socratic engine."""

from __future__ import annotations

import re
import uuid
from typing import Final

from stc.schemas.models import (
    ArchetypeDiff,
    ArchetypeOption,
    ConcernDimension,
    TreeOfConcerns,
)

# Normative threshold register from 01_INVARIANTS.md
TAU: Final[float] = 0.30
AMBIGUITY_TAU: Final[float] = 0.30

# Heuristic 2: Error and resilience terms
ERROR_KEYWORDS_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"\b(exception|exceptions|timeout|timeouts|retry|retries|backoff|fallback|fallbacks|"
    r"circuit\s*breaker|error\s*handling|grace\s*period|deadline)\b",
    re.IGNORECASE,
)

# Numeric threshold pattern (e.g. 30s, 3 retries, 100ms, 5 attempts, 85%)
NUMERIC_THRESHOLD_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"\b\d+(?:\.\d+)?\s*(?:s|sec|seconds?|ms|milliseconds?|m|min|minutes?|h|hours?|"
    r"times|retries|attempts?|failures?|x|%|percent)\b|"
    r"\b(?:timeout|retries|retry|backoff|limit|max|up to|after|within|initial|grace\s*period)"
    r"\s*(?:of|is|:)?\s*\d+(?:\.\d+)?\b|"
    r"\b\d+\s+(?:consecutive|subsequent)\b",
    re.IGNORECASE,
)

# Heuristic 3: Opposing architectural pattern pairs
OPPOSING_PATTERNS: Final[list[tuple[re.Pattern[str], re.Pattern[str], str]]] = [
    (
        re.compile(r"\bstateless\b", re.IGNORECASE),
        re.compile(r"\bin-memory session(?:\s+state)?\b|\bsession\s+state\b", re.IGNORECASE),
        "Stateless architecture vs In-memory session state",
    ),
    (
        re.compile(r"\bsync(?:hronous)?-only\b|\bstrictly synchronous\b", re.IGNORECASE),
        re.compile(r"\basync(?:hronous)?-only\b|\bevent-driven\b", re.IGNORECASE),
        "Synchronous-only execution vs Asynchronous event-driven",
    ),
    (
        re.compile(r"\bimmutable\b", re.IGNORECASE),
        re.compile(r"\bmutable\s+state\b|\bin-place\s+mutation\b", re.IGNORECASE),
        "Immutable data structures vs In-place mutable state",
    ),
    (
        re.compile(r"\bsingle-tenant\b", re.IGNORECASE),
        re.compile(r"\bmulti-tenant\b", re.IGNORECASE),
        "Single-tenant isolation vs Multi-tenant shared substrate",
    ),
    (
        re.compile(r"\bzero-dependency\b|\bno external dependencies\b", re.IGNORECASE),
        re.compile(r"\bthird-party\s+service\b|\bexternal\s+api\b", re.IGNORECASE),
        "Zero-dependency boundary vs Third-party external API integration",
    ),
    (
        re.compile(r"\bfail-closed\b", re.IGNORECASE),
        re.compile(r"\bfail-open\b", re.IGNORECASE),
        "Fail-closed strict security vs Fail-open high availability",
    ),
    (
        re.compile(r"\block-free\b", re.IGNORECASE),
        re.compile(r"\bdistributed\s+lock\b|\bmutex\b", re.IGNORECASE),
        "Lock-free concurrency vs Distributed lock / Mutex coordination",
    ),
]


def _has_non_empty_items(items: list[str]) -> bool:
    """Check if any string item in list contains non-whitespace content."""
    return any(item.strip() for item in items)


def _extract_all_toc_text(toc: TreeOfConcerns) -> str:
    """Extract all string items across all 5 dimensions of TreeOfConcerns."""
    lines: list[str] = [toc.spec_id]
    for d in [
        toc.domain_invariants,
        toc.persistence_storage,
        toc.communication_protocols,
        toc.boundary_security,
        toc.failure_resilience,
    ]:
        lines.extend(d.invariants)
        lines.extend(d.contracts)
        lines.extend(d.failure_modes)
        lines.extend(d.acceptance_tests)
    return "\n".join(lines)


def compute_missing_dimension_penalty(toc: TreeOfConcerns) -> float:
    """Missing Dimension Penalty: If any of 5 dimensions has empty rules, P_dim = 0.5."""
    dims: list[ConcernDimension] = [
        toc.domain_invariants,
        toc.persistence_storage,
        toc.communication_protocols,
        toc.boundary_security,
        toc.failure_resilience,
    ]
    for d in dims:
        has_rules = (
            _has_non_empty_items(d.invariants)
            or _has_non_empty_items(d.contracts)
            or _has_non_empty_items(d.failure_modes)
            or _has_non_empty_items(d.acceptance_tests)
        )
        if not has_rules:
            return 0.5
    return 0.0


def compute_error_policy_penalty(toc: TreeOfConcerns, raw_text: str = "") -> float:
    """Under-specified Error Policies: If exceptions or timeouts lack numbers, P_err = 0.3."""
    statements: list[str] = []
    for item in (
        toc.failure_resilience.invariants
        + toc.failure_resilience.contracts
        + toc.failure_resilience.failure_modes
        + toc.failure_resilience.acceptance_tests
    ):
        clean = item.strip()
        if clean:
            statements.append(clean)

    if raw_text.strip():
        for line in raw_text.splitlines():
            clean = line.strip()
            if clean:
                statements.append(clean)

    error_statements: list[str] = [s for s in statements if ERROR_KEYWORDS_PATTERN.search(s)]
    if not error_statements:
        return 0.0

    for stmt in error_statements:
        if not NUMERIC_THRESHOLD_PATTERN.search(stmt):
            return 0.3

    return 0.0


def compute_contradiction_penalty(
    raw_text: str = "",
    toc: TreeOfConcerns | None = None,
) -> float:
    """Contradiction Divergence: If terms match opposing architectural patterns, P_contra = 1.0."""
    texts: list[str] = []
    if raw_text.strip():
        texts.append(raw_text)
    if toc is not None:
        texts.append(_extract_all_toc_text(toc))
    combined = "\n".join(texts)
    if not combined.strip():
        return 0.0

    for pat_a, pat_b, _desc in OPPOSING_PATTERNS:
        if pat_a.search(combined) and pat_b.search(combined):
            return 1.0

    return 0.0


def compute_ambiguity_score(toc: TreeOfConcerns, raw_text: str = "") -> float:
    """Calculate the overall ambiguity score: min(1.0, P_dim + P_err + P_contra)."""
    p_dim = compute_missing_dimension_penalty(toc)
    p_err = compute_error_policy_penalty(toc, raw_text)
    p_contra = compute_contradiction_penalty(raw_text, toc=toc)
    total = p_dim + p_err + p_contra
    return min(1.0, round(total, 4))


def generate_archetype_diff(
    toc: TreeOfConcerns,
    raw_text: str = "",
) -> ArchetypeDiff:
    """Generate exactly two contrasting architectural archetypes (Alpha vs Beta) on trigger."""
    diff_uuid = uuid.uuid4().hex[:8]
    effective_text = f"{raw_text}\n{_extract_all_toc_text(toc)}".strip()

    # Check contradiction first
    for pat_a, pat_b, desc in OPPOSING_PATTERNS:
        if pat_a.search(effective_text) and pat_b.search(effective_text):
            terms = desc.split(" vs ")
            term_a = terms[0] if len(terms) > 0 else "Pattern A"
            term_b = terms[1] if len(terms) > 1 else "Pattern B"
            return ArchetypeDiff(
                diff_id=f"diff_{toc.spec_id}_{diff_uuid}",
                concern_dimension="domain_invariants",
                core_dilemma=f"Opposing Pattern Contradiction: {desc}",
                option_a=ArchetypeOption(
                    option_id="option_a",
                    title=f"Archetype Alpha ({term_a})",
                    tradeoff_pro=f"Strict compliance with {term_a}, zero state leakage.",
                    tradeoff_con=f"Requires strictly stateless callers; rejects {term_b}.",
                    invariants_to_lock=[f"System MUST strictly adhere to {term_a}."],
                ),
                option_b=ArchetypeOption(
                    option_id="option_b",
                    title=f"Archetype Beta ({term_b})",
                    tradeoff_pro=f"Permits {term_b} for high throughput and reduced latency.",
                    tradeoff_con="Requires eventual state synchronization and recovery mechanisms.",
                    invariants_to_lock=[
                        f"System MUST permit {term_b} with eventual reconciliation."
                    ],
                ),
            )

    # Check for domain-specific RRF / Rank normalization dilemma
    is_rrf = bool(
        re.search(r"\b(rrf|reciprocal\s*rank|fusion|rank)\b", effective_text, re.IGNORECASE)
        and re.search(r"\b(tie|tied|equal|rank)\b", effective_text, re.IGNORECASE)
    )
    if is_rrf:
        return ArchetypeDiff(
            diff_id=f"diff_{toc.spec_id}_{diff_uuid}",
            concern_dimension="domain_invariants",
            core_dilemma="Tied Rank Normalization Strategy",
            option_a=ArchetypeOption(
                option_id="option_a",
                title="Archetype Alpha (Deterministic Strict)",
                tradeoff_pro="Breaks ties by secondary document ID ascending; reproducible order.",
                tradeoff_con="Arbitrary tiebreaker ordering favors lower alphanumeric IDs.",
                invariants_to_lock=["Tied fusion ranks MUST break ties using doc_id ASC."],
            ),
            option_b=ArchetypeOption(
                option_id="option_b",
                title="Archetype Beta (Averaging Rank)",
                tradeoff_pro="Averages ranks across tied candidates with standard statistics.",
                tradeoff_con="Yields non-integer rank positions and fractional score complexity.",
                invariants_to_lock=[
                    "Tied fusion ranks MUST be averaged across equivalent score positions."
                ],
            ),
        )

    # Check if failure resilience triggered ambiguity
    p_err = compute_error_policy_penalty(toc, raw_text)
    res_has_rules = (
        _has_non_empty_items(toc.failure_resilience.invariants)
        or _has_non_empty_items(toc.failure_resilience.contracts)
        or _has_non_empty_items(toc.failure_resilience.failure_modes)
        or _has_non_empty_items(toc.failure_resilience.acceptance_tests)
    )
    if p_err > 0 or not res_has_rules:
        return ArchetypeDiff(
            diff_id=f"diff_{toc.spec_id}_{diff_uuid}",
            concern_dimension="failure_resilience",
            core_dilemma="Fault Tolerance & Error Recovery Strategy",
            option_a=ArchetypeOption(
                option_id="option_a",
                title="Archetype Alpha (Conservative / Fail-Closed)",
                tradeoff_pro=(
                    "Strict validation, immediate error propagation, synchronous verification, "
                    "high security, zero stale data allowance."
                ),
                tradeoff_con=(
                    "Lower throughput under transient faults, operations fail immediately on "
                    "first error."
                ),
                invariants_to_lock=[
                    "System MUST fail-closed with immediate error propagation and zero stale state."
                ],
            ),
            option_b=ArchetypeOption(
                option_id="option_b",
                title="Archetype Beta (Resilient / High-Throughput)",
                tradeoff_pro=(
                    "Grace windows, optimistic concurrency, asynchronous worker processing, "
                    "fallback buffers, eventually consistent state."
                ),
                tradeoff_con=(
                    "Potential temporary state divergence and delayed consistency resolution."
                ),
                invariants_to_lock=[
                    "System MUST allow optimistic execution with 30s grace windows and "
                    "asynchronous fallback buffers."
                ],
            ),
        )

    # Check persistence storage missing
    pers_has_rules = (
        _has_non_empty_items(toc.persistence_storage.invariants)
        or _has_non_empty_items(toc.persistence_storage.contracts)
        or _has_non_empty_items(toc.persistence_storage.failure_modes)
        or _has_non_empty_items(toc.persistence_storage.acceptance_tests)
    )
    if not pers_has_rules:
        return ArchetypeDiff(
            diff_id=f"diff_{toc.spec_id}_{diff_uuid}",
            concern_dimension="persistence_storage",
            core_dilemma="Persistence & Storage Model",
            option_a=ArchetypeOption(
                option_id="option_a",
                title="Archetype Alpha (ACID Relational / Strict SQLite)",
                tradeoff_pro=(
                    "Strong ACID transactional guarantees, immediate durability, strict "
                    "relational schema constraints."
                ),
                tradeoff_con="Write locking serialization bottleneck under high write concurrency.",
                invariants_to_lock=[
                    "All persistent state MUST be stored in SQLite with ACID transactions and "
                    "WAL mode."
                ],
            ),
            option_b=ArchetypeOption(
                option_id="option_b",
                title="Archetype Beta (Event-Sourced Append-Only)",
                tradeoff_pro=(
                    "Append-only high-speed ingestion, full audit history, non-blocking writes."
                ),
                tradeoff_con="Requires asynchronous read projection rebuilding and compaction.",
                invariants_to_lock=[
                    "All state mutations MUST be stored as append-only immutable events."
                ],
            ),
        )

    # Check communication protocols missing
    comm_has_rules = (
        _has_non_empty_items(toc.communication_protocols.invariants)
        or _has_non_empty_items(toc.communication_protocols.contracts)
        or _has_non_empty_items(toc.communication_protocols.failure_modes)
        or _has_non_empty_items(toc.communication_protocols.acceptance_tests)
    )
    if not comm_has_rules:
        return ArchetypeDiff(
            diff_id=f"diff_{toc.spec_id}_{diff_uuid}",
            concern_dimension="communication_protocols",
            core_dilemma="Communication & Transport Architecture",
            option_a=ArchetypeOption(
                option_id="option_a",
                title="Archetype Alpha (Synchronous PEP 544 Protocols)",
                tradeoff_pro=(
                    "Direct PEP 544 typed method invocations, deterministic stack traces, "
                    "zero transport latency."
                ),
                tradeoff_con=(
                    "Tight execution coupling between calling caller and receiving subsystem."
                ),
                invariants_to_lock=[
                    "Cross-subsystem calls MUST use synchronous PEP 544 Protocol interfaces."
                ],
            ),
            option_b=ArchetypeOption(
                option_id="option_b",
                title="Archetype Beta (Asynchronous Scoped Hormone Bus)",
                tradeoff_pro=(
                    "Decoupled cellular pub/sub messaging, non-blocking dispatch, natural "
                    "backpressure buffering."
                ),
                tradeoff_con=(
                    "Asynchronous causality tracking required, non-deterministic execution timing."
                ),
                invariants_to_lock=[
                    "Cross-subsystem communications MUST use asynchronous HormoneEvent pub/sub."
                ],
            ),
        )

    # Check boundary security missing
    sec_has_rules = (
        _has_non_empty_items(toc.boundary_security.invariants)
        or _has_non_empty_items(toc.boundary_security.contracts)
        or _has_non_empty_items(toc.boundary_security.failure_modes)
        or _has_non_empty_items(toc.boundary_security.acceptance_tests)
    )
    if not sec_has_rules:
        return ArchetypeDiff(
            diff_id=f"diff_{toc.spec_id}_{diff_uuid}",
            concern_dimension="boundary_security",
            core_dilemma="Boundary Isolation & Trust Model",
            option_a=ArchetypeOption(
                option_id="option_a",
                title="Archetype Alpha (Zero-Trust Isolated Sandbox)",
                tradeoff_pro=(
                    "Hermetic filesystem sandboxing, mandatory PII redaction, non-root execution."
                ),
                tradeoff_con=(
                    "Restricted subprocess capabilities, overhead of path translation and "
                    "boundary checks."
                ),
                invariants_to_lock=[
                    "Subsystems MUST execute inside isolated sandboxes with strict PII redaction."
                ],
            ),
            option_b=ArchetypeOption(
                option_id="option_b",
                title="Archetype Beta (Permissive In-Process Boundary)",
                tradeoff_pro="Full native OS and subprocess access, zero virtualization overhead.",
                tradeoff_con=(
                    "Requires cooperative isolation and trust in worker execution integrity."
                ),
                invariants_to_lock=[
                    "Subsystems execute in-process with cooperative memory isolation."
                ],
            ),
        )

    # Check domain invariants missing
    domain_has_rules = (
        _has_non_empty_items(toc.domain_invariants.invariants)
        or _has_non_empty_items(toc.domain_invariants.contracts)
        or _has_non_empty_items(toc.domain_invariants.failure_modes)
        or _has_non_empty_items(toc.domain_invariants.acceptance_tests)
    )
    if not domain_has_rules:
        return ArchetypeDiff(
            diff_id=f"diff_{toc.spec_id}_{diff_uuid}",
            concern_dimension="domain_invariants",
            core_dilemma="Domain Invariant Integrity & Enforcement Model",
            option_a=ArchetypeOption(
                option_id="option_a",
                title="Archetype Alpha (Strict Fail-Closed Invariants)",
                tradeoff_pro="Immediate invariant enforcement, zero undefined state transitions.",
                tradeoff_con=(
                    "Rejects any transaction with unvalidated fields or uncertain preconditions."
                ),
                invariants_to_lock=[
                    "Domain state transitions MUST be validated fail-closed before persistence."
                ],
            ),
            option_b=ArchetypeOption(
                option_id="option_b",
                title="Archetype Beta (Permissive Eventual Invariants)",
                tradeoff_pro="Optimistic invariant verification for high ingest throughput.",
                tradeoff_con="Requires downstream reconciliation and compensation logic.",
                invariants_to_lock=[
                    "Domain state transitions MAY be admitted optimistically with "
                    "eventual reconciliation."
                ],
            ),
        )

    # Default fallback: Conservative vs Resilient
    return ArchetypeDiff(
        diff_id=f"diff_{toc.spec_id}_{diff_uuid}",
        concern_dimension="domain_invariants",
        core_dilemma="Architectural Conservatism vs Throughput Resilience",
        option_a=ArchetypeOption(
            option_id="option_a",
            title="Archetype Alpha (Conservative / Fail-Closed)",
            tradeoff_pro=(
                "Strict validation, immediate error propagation, synchronous verification, "
                "high security, zero stale data allowance."
            ),
            tradeoff_con=(
                "Lower throughput under transient faults, operations fail immediately on "
                "first error."
            ),
            invariants_to_lock=[
                "System MUST fail-closed with immediate error propagation and zero stale state."
            ],
        ),
        option_b=ArchetypeOption(
            option_id="option_b",
            title="Archetype Beta (Resilient / High-Throughput)",
            tradeoff_pro=(
                "Grace windows, optimistic concurrency, asynchronous worker processing, "
                "fallback buffers, eventually consistent state."
            ),
            tradeoff_con=(
                "Potential temporary state divergence and delayed consistency resolution."
            ),
            invariants_to_lock=[
                "System MUST allow optimistic execution with 30s grace windows and "
                "asynchronous fallback buffers."
            ],
        ),
    )


def generate_archetype_diffs(
    toc: TreeOfConcerns,
    raw_text: str = "",
) -> list[ArchetypeDiff]:
    """Generate all detected contrasting architectural archetypes on tau trigger."""
    diffs: list[ArchetypeDiff] = []
    seen_dilemmas: set[str] = set()

    primary_diff = generate_archetype_diff(toc, raw_text=raw_text)
    diffs.append(primary_diff)
    seen_dilemmas.add(primary_diff.core_dilemma)

    return diffs


__all__ = [
    "AMBIGUITY_TAU",
    "OPPOSING_PATTERNS",
    "TAU",
    "compute_ambiguity_score",
    "compute_contradiction_penalty",
    "compute_error_policy_penalty",
    "compute_missing_dimension_penalty",
    "generate_archetype_diff",
    "generate_archetype_diffs",
]
