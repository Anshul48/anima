"""Unit tests for the Socratic decomposition and ambiguity detection engine.

Enforces zero-mock verification:
- Real SpecAtom instances and markdown parsing
- Exact deterministic heuristic verification (P_dim, P_err, P_contra)
- Normative threshold tau = 0.30 enforcement
- Pairwise ArchetypeDiff generation (exactly two opposing archetypes)
- Real file locking with cryptographic SHA-256 checksums
- Real CliRunner invocations of `stc spec` with TOC table and 2-choice prompt
"""

from __future__ import annotations

import hashlib
import inspect
import json
import re
from collections.abc import Iterator
from pathlib import Path

import pytest
from click.testing import CliRunner

from stc.cli import main
from stc.core.config import get_settings
from stc.protocols.interfaces import SocraticDecomposerProtocol
from stc.schemas.models import (
    ConcernDimension,
    SpecAtom,
    TreeOfConcerns,
)
from stc.socratic.ambiguity import (
    TAU,
    compute_ambiguity_score,
    compute_contradiction_penalty,
    compute_error_policy_penalty,
    compute_missing_dimension_penalty,
    generate_archetype_diff,
    generate_archetype_diffs,
)
from stc.socratic.decomposer import SocraticDecomposer


@pytest.fixture(autouse=True)
def _disposable_runtime_roots(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Redirect gate-generated state to per-test disposable locations (R1).

    CLI-invoking tests in this file drive pipeline writers (locked
    invariants, signed receipts, trace DB rows, leased worktrees); all
    land under tmp_path so the gated repository stays byte-neutral.
    """
    roots = tmp_path / "stc-runtime"
    monkeypatch.setenv("STC_INVARIANTS_DIR", str(roots / "invariants"))
    monkeypatch.setenv("STC_RECEIPTS_DIR", str(roots / "receipts"))
    monkeypatch.setenv("STC_TRACE_DB_PATH", str(roots / "trace.db"))
    monkeypatch.setenv("STC_WORKTREE_ROOT", str(roots / "worktrees"))
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _make_spec_atom(spec_id: str, content: str, source_path: str = "spec.md") -> SpecAtom:
    """Helper to construct a valid SpecAtom with computed sha256."""
    sha = hashlib.sha256(content.encode("utf-8")).hexdigest()
    return SpecAtom(
        spec_id=spec_id,
        source_path=source_path,
        raw_content=content,
        content_sha256=sha,
    )


def test_socratic_decomposer_protocol_conformance() -> None:
    """Verify that SocraticDecomposer satisfies PEP 544 SocraticDecomposerProtocol."""
    decomposer = SocraticDecomposer()
    assert isinstance(decomposer, SocraticDecomposerProtocol)


def test_socratic_protocol_signatures_cover_impl_kwargs() -> None:
    """Protocol declares the impl kwargs protocol-typed callers may use."""
    for name in ("detect_ambiguity", "lock_invariants"):
        proto = inspect.signature(getattr(SocraticDecomposerProtocol, name))
        impl = inspect.signature(getattr(SocraticDecomposer, name))
        for param, details in proto.parameters.items():
            assert param in impl.parameters, f"{name}: impl missing {param!r}"
            if details.default is not inspect.Parameter.empty:
                assert impl.parameters[param].default == details.default


def test_decompose_complete_spec_score_below_tau() -> None:
    """Complete spec with all 5 dimensions and numeric resilience thresholds passes tau."""
    content = (
        "# Complete Feature Specification\n\n"
        "## Domain Invariants\n"
        "- Account balance must never drop below zero.\n"
        "- Task receipts must be cryptographically signed.\n\n"
        "## Persistence & Storage\n"
        "- SQLite database with WAL mode enabled.\n"
        "- Schema tables for documents and proposals.\n\n"
        "## Communication Protocols\n"
        "- PEP 544 typed interfaces across subsystem membranes.\n"
        "- JSON-RPC endpoint handlers.\n\n"
        "## Boundary & Security\n"
        "- Isolated worktree execution environment.\n"
        "- Strict PII redaction on input text.\n\n"
        "## Failure Resilience\n"
        "- Retry up to 3 times with exponential backoff (initial 100ms, max 5s).\n"
        "- Circuit breaker trips after 5 consecutive failures with 30s timeout.\n"
    )
    atom = _make_spec_atom("complete_feature", content)
    decomposer = SocraticDecomposer()
    toc = decomposer.decompose(atom)

    assert toc.spec_id == "complete_feature"
    assert len(toc.domain_invariants.invariants) >= 2
    assert len(toc.persistence_storage.contracts) >= 2
    assert len(toc.communication_protocols.contracts) >= 2
    assert len(toc.boundary_security.contracts) >= 2
    assert len(toc.failure_resilience.failure_modes) >= 2

    # Score must be strictly below tau = 0.30
    assert toc.ambiguity_score < TAU
    assert toc.ambiguity_score == 0.0

    # No archetype diffs generated
    diffs = decomposer.detect_ambiguity(toc, raw_text=content)
    assert diffs == []


def test_missing_dimension_triggers_penalty() -> None:
    """Spec missing one or more dimensions incurs P_dim = 0.5 penalty."""
    content = (
        "# Incomplete Feature\n\n"
        "## Domain Invariants\n"
        "- Invariant rule.\n\n"
        "## Communication Protocols\n"
        "- PEP 544 Protocol.\n\n"
        "## Boundary & Security\n"
        "- Sandbox boundary.\n\n"
        "## Failure Resilience\n"
        "- Timeout 30s.\n"
    )
    atom = _make_spec_atom("missing_storage", content)
    decomposer = SocraticDecomposer()
    toc = decomposer.decompose(atom)

    # Persistence storage is missing
    assert len(toc.persistence_storage.contracts) == 0
    penalty = compute_missing_dimension_penalty(toc)
    assert penalty == 0.5
    assert toc.ambiguity_score >= 0.5
    assert toc.ambiguity_score >= TAU

    diffs = decomposer.detect_ambiguity(toc, raw_text=content)
    assert len(diffs) == 1
    diff = diffs[0]
    assert diff.concern_dimension == "persistence_storage"
    assert diff.option_a.option_id == "option_a"
    assert diff.option_b.option_id == "option_b"


def test_underspecified_error_policy_triggers_penalty() -> None:
    """Spec mentioning retries/timeouts without numeric thresholds incurs P_err = 0.3."""
    content = (
        "# Ambiguous Resilience Feature\n\n"
        "## Domain Invariants\n"
        "- Transaction idempotency required.\n\n"
        "## Persistence & Storage\n"
        "- SQLite FTS5 table index.\n\n"
        "## Communication Protocols\n"
        "- Subsystem typed interfaces.\n\n"
        "## Boundary & Security\n"
        "- Read-only directory permissions.\n\n"
        "## Failure Resilience\n"
        "- Retry with backoff on failure.\n"
    )
    atom = _make_spec_atom("underspec_resilience", content)
    decomposer = SocraticDecomposer()
    toc = decomposer.decompose(atom)

    p_dim = compute_missing_dimension_penalty(toc)
    assert p_dim == 0.0

    p_err = compute_error_policy_penalty(toc, content)
    assert p_err == 0.3

    assert toc.ambiguity_score >= TAU
    diffs = decomposer.detect_ambiguity(toc, raw_text=content)
    assert len(diffs) == 1
    diff = diffs[0]
    assert diff.concern_dimension == "failure_resilience"
    assert "Conservative / Fail-Closed" in diff.option_a.title
    assert "Resilient / High-Throughput" in diff.option_b.title


def test_contradiction_divergence_triggers_penalty() -> None:
    """Spec with opposing architectural patterns incurs P_contra = 1.0 penalty."""
    content = (
        "# Contradictory Architecture\n\n"
        "## Domain Invariants\n"
        "- Stateless processing with in-memory session state.\n\n"
        "## Persistence & Storage\n"
        "- SQLite tables.\n\n"
        "## Communication Protocols\n"
        "- PEP 544 Protocols.\n\n"
        "## Boundary & Security\n"
        "- Sandbox boundary.\n\n"
        "## Failure Resilience\n"
        "- Timeout 10s.\n"
    )
    atom = _make_spec_atom("contradiction_spec", content)
    decomposer = SocraticDecomposer()
    toc = decomposer.decompose(atom)

    p_contra = compute_contradiction_penalty(content)
    assert p_contra == 1.0
    assert toc.ambiguity_score == 1.0
    assert toc.ambiguity_score >= TAU

    diffs = decomposer.detect_ambiguity(toc, raw_text=content)
    assert len(diffs) == 1
    assert "Contradiction" in diffs[0].core_dilemma


def test_archetype_options_contrast_and_properties() -> None:
    """Verify generated ArchetypeDiff has exactly two opposing, valid options."""
    dim = ConcernDimension(
        dimension_name="failure_resilience",
        failure_modes=["Retry with backoff"],
    )
    toc = TreeOfConcerns(
        spec_id="test_contrast",
        domain_invariants=ConcernDimension(dimension_name="domain_invariants", invariants=["Inv"]),
        persistence_storage=ConcernDimension(
            dimension_name="persistence_storage", contracts=["DB"]
        ),
        communication_protocols=ConcernDimension(
            dimension_name="communication_protocols", contracts=["API"]
        ),
        boundary_security=ConcernDimension(dimension_name="boundary_security", contracts=["Sec"]),
        failure_resilience=dim,
        ambiguity_score=0.30,
    )
    diff = generate_archetype_diff(toc, raw_text="Retry with backoff")

    assert diff.option_a.option_id == "option_a"
    assert diff.option_b.option_id == "option_b"
    assert len(diff.option_a.title) >= 5
    assert len(diff.option_b.title) >= 5
    assert diff.option_a.tradeoff_pro != diff.option_b.tradeoff_pro
    assert diff.option_a.tradeoff_con != diff.option_b.tradeoff_con
    assert len(diff.option_a.invariants_to_lock) > 0
    assert len(diff.option_b.invariants_to_lock) > 0

    # Alpha must be fail-closed/conservative, Beta must be resilient/grace-window
    is_alpha_fail_closed = (
        "fail-closed" in diff.option_a.title.lower()
        or "conservative" in diff.option_a.title.lower()
    )
    assert is_alpha_fail_closed
    is_beta_resilient = (
        "resilient" in diff.option_b.title.lower() or "throughput" in diff.option_b.title.lower()
    )
    assert is_beta_resilient


def test_rrf_domain_archetype_diff() -> None:
    """Verify RRF rank tiebreaker dilemma is synthesized for RRF specifications."""
    dim = ConcernDimension(
        dimension_name="failure_resilience",
        failure_modes=["Timeout 30s"],
    )
    toc = TreeOfConcerns(
        spec_id="feature_rrf",
        domain_invariants=ConcernDimension(
            dimension_name="domain_invariants",
            invariants=["Fusion weights sum to 1.0"],
        ),
        persistence_storage=ConcernDimension(
            dimension_name="persistence_storage",
            contracts=["SQLite FTS5"],
        ),
        communication_protocols=ConcernDimension(
            dimension_name="communication_protocols",
            contracts=["FusionEngine"],
        ),
        boundary_security=ConcernDimension(
            dimension_name="boundary_security",
            contracts=["Memory sandbox"],
        ),
        failure_resilience=dim,
        ambiguity_score=0.30,
    )
    diff = generate_archetype_diff(
        toc,
        raw_text="RRF reciprocal rank fusion tied rank normalization",
    )

    assert diff.core_dilemma == "Tied Rank Normalization Strategy"
    assert "Deterministic Strict" in diff.option_a.title
    assert "Averaging Rank" in diff.option_b.title
    assert any("doc_id ASC" in inv for inv in diff.option_a.invariants_to_lock)
    assert any("averaged" in inv for inv in diff.option_b.invariants_to_lock)


def test_lock_invariants_writes_file_and_checksum(tmp_path: Path) -> None:
    """Verify lock_invariants writes real file with [INVARIANT] tags and SHA-256 checksum."""
    decomposer = SocraticDecomposer()
    content = (
        "# Auth Spec\n"
        "## Domain Invariants\n- Must validate signature.\n"
        "## Persistence & Storage\n- SQLite.\n"
        "## Communication Protocols\n- Protocol.\n"
        "## Boundary & Security\n- Sandbox.\n"
        "## Failure Resilience\n- Retry with backoff.\n"
    )
    atom = _make_spec_atom("test_auth_lock", content)
    toc = decomposer.decompose(atom)

    target_file = tmp_path / "LOCKED_INVARIANTS.md"
    written_path = decomposer.lock_invariants(toc, [1], output_path=target_file)

    assert written_path == target_file
    assert target_file.is_file()

    saved_text = target_file.read_text(encoding="utf-8")
    assert "# Locked Invariants: test_auth_lock" in saved_text
    assert "Selected Archetype: Archetype Alpha" in saved_text
    assert "- [INVARIANT]" in saved_text
    assert "SHA-256 Checksum:" in saved_text

    # Verify SHA-256 integrity
    match = re.search(r"\*\*SHA-256 Checksum:\*\* `([a-f0-9]{64})`", saved_text)
    assert match is not None
    recorded_sha = match.group(1)

    payload = saved_text[: saved_text.index("\n---\n**SHA-256 Checksum:**")]
    computed_sha = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    assert recorded_sha == computed_sha


def test_lock_invariants_selection_choice_2(tmp_path: Path) -> None:
    """Verify selection of choice 2 locks Option Beta invariant."""
    decomposer = SocraticDecomposer()
    content = (
        "# Resilience Spec\n"
        "## Domain Invariants\n- Token check.\n"
        "## Persistence & Storage\n- SQLite.\n"
        "## Communication Protocols\n- Protocol.\n"
        "## Boundary & Security\n- Isolation.\n"
        "## Failure Resilience\n- Retry on error.\n"
    )
    atom = _make_spec_atom("test_beta_lock", content)
    toc = decomposer.decompose(atom)

    target_file = tmp_path / "BETA_INVARIANTS.md"
    decomposer.lock_invariants(toc, [2], output_path=target_file)

    saved_text = target_file.read_text(encoding="utf-8")
    assert "Archetype Beta (Resilient / High-Throughput)" in saved_text
    assert "optimistic execution" in saved_text


def test_cli_spec_complete_spec_no_prompt(tmp_path: Path) -> None:
    """stc spec on a complete specification displays TOC table without prompt."""
    spec_path = tmp_path / "complete_spec.md"
    spec_path.write_text(
        "# Clean Service Spec\n\n"
        "## Domain Invariants\n- Strict validation rules.\n\n"
        "## Persistence & Storage\n- Relational tables.\n\n"
        "## Communication Protocols\n- PEP 544 typed interfaces.\n\n"
        "## Boundary & Security\n- Worktree sandbox isolation.\n\n"
        "## Failure Resilience\n- Timeout 30s with 3 retries and 100ms backoff.\n",
        encoding="utf-8",
    )
    runner = CliRunner()
    res = runner.invoke(main, ["spec", str(spec_path)])

    assert res.exit_code == 0
    assert "Tree of Concerns (TOC) Decomposition" in res.output
    assert "Domain Invariants" in res.output
    assert "Specification validated with zero ambiguous dilemmas." in res.output
    assert "ARCHETYPE DILEMMA DETECTED" not in res.output


def test_cli_spec_ambiguous_presents_2_choice_prompt_and_locks(tmp_path: Path) -> None:
    """stc spec on ambiguous spec presents 2-choice prompt and locks selected archetype."""
    spec_path = tmp_path / "ambiguous_spec.md"
    spec_path.write_text(
        "# Ambiguous Service Spec\n\n"
        "## Domain Invariants\n- Must check auth tokens.\n\n"
        "## Persistence & Storage\n- SQLite tables.\n\n"
        "## Communication Protocols\n- REST endpoints.\n\n"
        "## Boundary & Security\n- Internal sandbox.\n\n"
        "## Failure Resilience\n- Retry with backoff.\n",
        encoding="utf-8",
    )
    runner = CliRunner()
    # Provide choice 1 as input
    res = runner.invoke(main, ["spec", str(spec_path)], input="1\n")

    assert res.exit_code == 0
    assert "Tree of Concerns (TOC) Decomposition" in res.output
    assert "High ambiguity detected" in res.output
    assert "ARCHETYPE DILEMMA DETECTED" in res.output
    assert "(1) Archetype Alpha" in res.output
    assert "(2) Archetype Beta" in res.output
    assert "Select choice [1/2]" in res.output
    assert "Invariant locked:" in res.output
    assert "Written to" in res.output


def test_cli_spec_ambiguous_choice_2(tmp_path: Path) -> None:
    """stc spec with choice 2 locks Option Beta."""
    spec_path = tmp_path / "ambiguous_spec_2.md"
    spec_path.write_text(
        "# Ambiguous Service Spec 2\n\n"
        "## Domain Invariants\n- Account rules.\n\n"
        "## Persistence & Storage\n- SQLite tables.\n\n"
        "## Communication Protocols\n- REST endpoints.\n\n"
        "## Boundary & Security\n- Internal sandbox.\n\n"
        "## Failure Resilience\n- Retry with backoff.\n",
        encoding="utf-8",
    )
    runner = CliRunner()
    res = runner.invoke(main, ["spec", str(spec_path)], input="2\n")

    assert res.exit_code == 0
    assert "Invariant locked:" in res.output
    assert "optimistic execution" in res.output


def test_cli_spec_json_mode(tmp_path: Path) -> None:
    """stc -j spec outputs valid JSON with ambiguity status and archetype diffs."""
    spec_path = tmp_path / "json_test_spec.md"
    spec_path.write_text(
        "# JSON Test Spec\n\n"
        "## Domain Invariants\n- Rule 1.\n\n"
        "## Persistence & Storage\n- SQLite.\n\n"
        "## Communication Protocols\n- Interface.\n\n"
        "## Boundary & Security\n- Sandbox.\n\n"
        "## Failure Resilience\n- Retry on error.\n",
        encoding="utf-8",
    )
    runner = CliRunner()
    res = runner.invoke(main, ["-j", "spec", str(spec_path)])

    assert res.exit_code == 0
    data = json.loads(res.output)
    assert data["spec_atom"]["spec_id"] == "json_test_spec"
    assert "tree_of_concerns" in data
    assert data["ambiguity_detected"] is True
    assert len(data["archetype_diffs"]) == 1
    diff = data["archetype_diffs"][0]
    assert diff["option_a"]["option_id"] == "option_a"
    assert diff["option_b"]["option_id"] == "option_b"


def test_cli_spec_on_sample_spec(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Physical exit gate: stc spec on sample_spec.md renders TOC table and 2-choice prompt."""
    sample_spec_path = Path("specs/sample_spec.md")
    assert sample_spec_path.is_file()
    inv_dir = tmp_path / "inv"
    monkeypatch.setenv("STC_INVARIANTS_DIR", str(inv_dir))

    runner = CliRunner()
    res = runner.invoke(main, ["spec", str(sample_spec_path)], input="1\n")

    assert res.exit_code == 0
    assert "Tree of Concerns (TOC) Decomposition" in res.output
    assert "Ambiguity Score: 0.30 [THRESHOLD EXCEEDED: >= 0.30]" in res.output
    assert "ARCHETYPE DILEMMA DETECTED: Fault Tolerance & Error Recovery Strategy" in res.output
    assert "(1) Archetype Alpha (Conservative / Fail-Closed)" in res.output
    assert "(2) Archetype Beta (Resilient / High-Throughput)" in res.output
    assert "Select choice [1/2]" in res.output
    locked_needle = "System MUST fail-closed with immediate error propagation"
    assert locked_needle in res.output
    expected = str(inv_dir / "SAMPLE_SPEC_INVARIANTS.md").replace("\\", "/")
    flat_output = res.output.replace("\\", "/").replace("\n", "")
    assert f"Written to {expected}" in flat_output
    assert (inv_dir / "SAMPLE_SPEC_INVARIANTS.md").is_file()


def test_cli_spec_abort_routes_to_circuit_fail(tmp_path: Path) -> None:
    """Aborting the Sovereign choice (EOF / Ctrl-C) must fail closed, never silently default."""
    spec_path = tmp_path / "abort_spec.md"
    spec_path.write_text(
        "# Abort Spec\n\n"
        "## Domain Invariants\n- Must check auth tokens.\n\n"
        "## Persistence & Storage\n- SQLite tables.\n\n"
        "## Communication Protocols\n- REST endpoints.\n\n"
        "## Boundary & Security\n- Internal sandbox.\n\n"
        "## Failure Resilience\n- Retry with backoff.\n",
        encoding="utf-8",
    )
    runner = CliRunner()
    # Zero-mock: Empty input stream produces EOF at click.prompt, raising click.Abort
    res = runner.invoke(main, ["spec", str(spec_path)], input="")

    assert res.exit_code != 0
    assert "CIRCUIT_FAIL" in res.output
    assert "no invariant locked" in res.output.lower()


def test_nested_subsections_retained_in_toc() -> None:
    """Nested subsections (###) must not cause subsequent items to be dropped."""
    content = (
        "# Service Spec\n\n"
        "## Domain Invariants\n"
        "### Core Business Logic\n"
        "- Account balance must not drop below zero.\n"
        "- Transaction receipts must be immutable.\n\n"
        "## Persistence & Storage\n"
        "### Relational Schema\n"
        "- SQLite users table.\n\n"
        "## Communication Protocols\n"
        "- PEP 544 Protocol.\n\n"
        "## Boundary & Security\n"
        "- Worktree sandbox.\n\n"
        "## Failure Resilience\n"
        "- Timeout 30s.\n"
    )
    atom = _make_spec_atom("test_nested_subsections", content)
    decomposer = SocraticDecomposer()
    toc = decomposer.decompose(atom)

    assert len(toc.domain_invariants.invariants) == 2
    assert "Account balance must not drop below zero." in toc.domain_invariants.invariants
    assert "Transaction receipts must be immutable." in toc.domain_invariants.invariants
    assert "SQLite users table." in toc.persistence_storage.contracts


def test_author_metadata_not_misclassified_as_security() -> None:
    """Author metadata headings must not pollute boundary_security contracts."""
    content = (
        "# Author: Alice Smith\n"
        "Created by team vanguard.\n\n"
        "## Domain Invariants\n"
        "- Invariant rule.\n\n"
        "## Persistence & Storage\n"
        "- SQLite.\n\n"
        "## Communication Protocols\n"
        "- Protocol.\n\n"
        "## Boundary & Security\n"
        "- Hermetic sandbox.\n\n"
        "## Failure Resilience\n"
        "- Timeout 30s.\n"
    )
    atom = _make_spec_atom("test_author_metadata", content)
    decomposer = SocraticDecomposer()
    toc = decomposer.decompose(atom)

    assert "Created by team vanguard." not in toc.boundary_security.contracts
    assert "Hermetic sandbox." in toc.boundary_security.contracts


def test_html_comments_and_tags_cleaned() -> None:
    """HTML comments must be dropped and HTML tags cleaned from extracted rules."""
    content = (
        "# Clean Service Spec\n\n"
        "## Domain Invariants\n"
        "<!-- This is an internal author comment -->\n"
        "<p>Must enforce token expiry.</p>\n"
        "- <strong>Zero debt</strong> state.\n\n"
        "## Persistence & Storage\n"
        "- SQLite database.\n\n"
        "## Communication Protocols\n"
        "- PEP 544 Protocol.\n\n"
        "## Boundary & Security\n"
        "- Sandbox.\n\n"
        "## Failure Resilience\n"
        "- Timeout 30s.\n"
    )
    atom = _make_spec_atom("test_html_clean", content)
    decomposer = SocraticDecomposer()
    toc = decomposer.decompose(atom)

    assert not any("<!--" in inv for inv in toc.domain_invariants.invariants)
    assert "Must enforce token expiry." in toc.domain_invariants.invariants
    assert "Zero debt state." in toc.domain_invariants.invariants


def test_error_policy_rule_numbering_not_treated_as_threshold() -> None:
    """List numbers like 'Rule 1:' must not be treated as numeric thresholds for error policies."""
    content = (
        "# Numbered Rule Spec\n\n"
        "## Domain Invariants\n"
        "- Strict rules.\n\n"
        "## Persistence & Storage\n"
        "- Database.\n\n"
        "## Communication Protocols\n"
        "- PEP 544 Protocol.\n\n"
        "## Boundary & Security\n"
        "- Sandbox.\n\n"
        "## Failure Resilience\n"
        "- Rule 1: Retry on failure.\n"
    )
    atom = _make_spec_atom("test_numbered_rule", content)
    decomposer = SocraticDecomposer()
    toc = decomposer.decompose(atom)

    p_err = compute_error_policy_penalty(toc, content)
    assert p_err == 0.3
    assert toc.ambiguity_score >= TAU


def test_mixed_resilience_items_detects_underspecified() -> None:
    """A threshold in one item must not mask an under-specified error policy in another."""
    dim = ConcernDimension(
        dimension_name="failure_resilience",
        failure_modes=[
            "Circuit breaker trips after 5 consecutive failures with 30s timeout.",
            "Retry on failure.",
        ],
    )
    toc = TreeOfConcerns(
        spec_id="test_mixed_resilience",
        domain_invariants=ConcernDimension(
            dimension_name="domain_invariants", invariants=["Rule 1"]
        ),
        persistence_storage=ConcernDimension(
            dimension_name="persistence_storage", contracts=["DB"]
        ),
        communication_protocols=ConcernDimension(
            dimension_name="communication_protocols", contracts=["Proto"]
        ),
        boundary_security=ConcernDimension(dimension_name="boundary_security", contracts=["Sec"]),
        failure_resilience=dim,
        ambiguity_score=0.0,
    )
    p_err = compute_error_policy_penalty(toc)
    assert p_err == 0.3


def test_contradiction_detected_from_toc_without_raw_text() -> None:
    """Contradiction must be detected from TreeOfConcerns content alone without raw_text."""
    toc = TreeOfConcerns(
        spec_id="test_contra_structured",
        domain_invariants=ConcernDimension(
            dimension_name="domain_invariants",
            invariants=["Stateless architecture with in-memory session state"],
        ),
        persistence_storage=ConcernDimension(
            dimension_name="persistence_storage", contracts=["DB"]
        ),
        communication_protocols=ConcernDimension(
            dimension_name="communication_protocols", contracts=["Proto"]
        ),
        boundary_security=ConcernDimension(dimension_name="boundary_security", contracts=["Sec"]),
        failure_resilience=ConcernDimension(
            dimension_name="failure_resilience", failure_modes=["Timeout 30s"]
        ),
        ambiguity_score=0.0,
    )
    score = compute_ambiguity_score(toc)
    assert score == 1.0

    decomposer = SocraticDecomposer()
    diffs = decomposer.detect_ambiguity(toc.model_copy(update={"ambiguity_score": score}))
    assert len(diffs) >= 1
    assert "Contradiction" in diffs[0].core_dilemma


def test_rrf_detected_from_toc_without_raw_text() -> None:
    """RRF dilemma must be detected from TreeOfConcerns content alone without raw_text."""
    toc = TreeOfConcerns(
        spec_id="feature_rrf_structured",
        domain_invariants=ConcernDimension(
            dimension_name="domain_invariants",
            invariants=["Reciprocal rank fusion tied rank normalization"],
        ),
        persistence_storage=ConcernDimension(
            dimension_name="persistence_storage", contracts=["DB"]
        ),
        communication_protocols=ConcernDimension(
            dimension_name="communication_protocols", contracts=["Proto"]
        ),
        boundary_security=ConcernDimension(dimension_name="boundary_security", contracts=["Sec"]),
        failure_resilience=ConcernDimension(
            dimension_name="failure_resilience", failure_modes=["Timeout 30s"]
        ),
        ambiguity_score=0.30,
    )
    diff = generate_archetype_diff(toc)
    assert diff.core_dilemma == "Tied Rank Normalization Strategy"
    assert "Deterministic Strict" in diff.option_a.title


def test_missing_domain_invariants_dilemma() -> None:
    """Missing domain invariants produces a domain invariants integrity dilemma."""
    toc = TreeOfConcerns(
        spec_id="missing_domain_spec",
        domain_invariants=ConcernDimension(dimension_name="domain_invariants"),
        persistence_storage=ConcernDimension(
            dimension_name="persistence_storage", contracts=["DB"]
        ),
        communication_protocols=ConcernDimension(
            dimension_name="communication_protocols", contracts=["Proto"]
        ),
        boundary_security=ConcernDimension(dimension_name="boundary_security", contracts=["Sec"]),
        failure_resilience=ConcernDimension(
            dimension_name="failure_resilience", failure_modes=["Timeout 30s"]
        ),
        ambiguity_score=0.50,
    )
    diff = generate_archetype_diff(toc)
    assert diff.concern_dimension == "domain_invariants"
    assert diff.core_dilemma == "Domain Invariant Integrity & Enforcement Model"
    assert "Strict Fail-Closed Invariants" in diff.option_a.title
    assert "Permissive Eventual Invariants" in diff.option_b.title


def test_generate_archetype_diffs_helper() -> None:
    """Verify generate_archetype_diffs returns non-empty list with valid diff."""
    toc = TreeOfConcerns(
        spec_id="test_diffs_helper",
        domain_invariants=ConcernDimension(dimension_name="domain_invariants", invariants=["Inv"]),
        persistence_storage=ConcernDimension(
            dimension_name="persistence_storage", contracts=["DB"]
        ),
        communication_protocols=ConcernDimension(
            dimension_name="communication_protocols", contracts=["Proto"]
        ),
        boundary_security=ConcernDimension(dimension_name="boundary_security", contracts=["Sec"]),
        failure_resilience=ConcernDimension(dimension_name="failure_resilience"),
        ambiguity_score=0.50,
    )
    diffs = generate_archetype_diffs(toc)
    assert len(diffs) >= 1
    assert diffs[0].option_a.option_id == "option_a"
    assert diffs[0].option_b.option_id == "option_b"
