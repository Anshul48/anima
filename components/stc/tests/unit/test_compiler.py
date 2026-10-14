"""Unit tests for the Context Compiler and Project Trace Hippocampus connector.

Enforces zero-mock verification per 01_INVARIANTS.md & 06_VERIFICATION_AND_TEST_HARNESS.md:
- Real SQLite temporary database with FTS5 lexical indexing, atoms, and proposals.
- Real SpecAtom instances and Tree of Concerns decompositions.
- Exact 25,600-byte context ceiling enforcement.
- Hierarchical context pruning dropping low-ranking episodic traces while preserving
  Neocortex invariants.
- Fail-closed BundleSizeExceededError on non-prunable budget breach.
- Performance exit gate: compilation completes in < 200ms.
- Full CLI integration testing for `stc compile`.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from pathlib import Path

import yaml
from click.testing import CliRunner

from stc.cli import main
from stc.compiler.bundler import ContextCompiler
from stc.core.errors import BundleSizeExceededError, TraceMemoryError
from stc.memory.trace_client import TraceClient
from stc.protocols.interfaces import ContextCompilerProtocol, TraceMemoryProtocol
from stc.schemas.models import (
    ConcernDimension,
    FileTarget,
    SpecAtom,
    TaskBundle,
    TreeOfConcerns,
)


def _create_spec_atom(spec_id: str, content: str) -> SpecAtom:
    """Helper to create a validated SpecAtom."""
    sha = hashlib.sha256(content.encode("utf-8")).hexdigest()
    return SpecAtom(
        spec_id=spec_id,
        source_path=f"specs/{spec_id}.md",
        raw_content=content,
        content_sha256=sha,
    )


def _create_test_toc(spec_id: str, invariants: list[str] | None = None) -> TreeOfConcerns:
    """Helper to create a validated TreeOfConcerns."""
    return TreeOfConcerns(
        spec_id=spec_id,
        domain_invariants=ConcernDimension(
            dimension_name="domain_invariants",
            invariants=invariants
            or [
                "Account balance must never drop below zero.",
                "Zero mock certification policy.",
                "Deterministic exit code 0 required.",
            ],
        ),
        persistence_storage=ConcernDimension(
            dimension_name="persistence_storage",
            contracts=["SQLite session tables with WAL mode."],
        ),
        communication_protocols=ConcernDimension(
            dimension_name="communication_protocols",
            contracts=["PEP 544 AuthGatewayProtocol."],
        ),
        boundary_security=ConcernDimension(
            dimension_name="boundary_security",
            contracts=["PII redaction enabled."],
        ),
        failure_resilience=ConcernDimension(
            dimension_name="failure_resilience",
            failure_modes=["Retry up to 3 times with exponential backoff."],
        ),
        ambiguity_score=0.10,
    )


def _populate_test_trace_db(db_path: Path) -> TraceClient:
    """Helper to create and populate a physical SQLite Trace database."""
    client = TraceClient(db_path=db_path)
    client.init_schema()

    client.insert_document("doc_001", "adr_concurrency.md", "architecture")
    client.insert_document("doc_002", "postmortem_deadlock.md", "incidents")

    client.insert_atom(
        "atom_001",
        "doc_001",
        "Use reciprocal rank fusion algorithm for normalized tie breaking.",
    )
    client.insert_atom(
        "atom_002",
        "doc_001",
        "Token bucket rate limiters provide deterministic burst bounds.",
    )
    client.insert_atom(
        "atom_003",
        "doc_002",
        "Named pipes on Windows cause deadlocks during async subprocess IO.",
    )

    client.insert_proposal(
        proposal_id="prop_inh_001",
        status="REFUTED",
        proposal_type="negative_inhibitor",
        decision_reason=(
            "Do not use Windows named pipes for inter-process communication; "
            "use localhost TCP sockets"
        ),
        candidate_json=json.dumps({"component": "transport", "failure": "deadlock"}),
        component="transport",
        created_event_id=101,
    )
    client.insert_proposal(
        proposal_id="prop_inh_002",
        status="REJECTED",
        proposal_type="negative_inhibitor",
        decision_reason="Do not use in-memory global state for multi-worker tasks",
        candidate_json=json.dumps({"component": "auth", "failure": "race_condition"}),
        component="auth",
        created_event_id=102,
    )
    return client


# =====================================================================
# Protocol Conformance Tests
# =====================================================================


def test_trace_client_protocol_conformance(tmp_path: Path) -> None:
    """Verify TraceClient satisfies TraceMemoryProtocol."""
    db_file = tmp_path / "trace.db"
    client = TraceClient(db_path=db_file)
    assert isinstance(client, TraceMemoryProtocol)


def test_context_compiler_protocol_conformance() -> None:
    """Verify ContextCompiler satisfies ContextCompilerProtocol."""
    compiler = ContextCompiler()
    assert isinstance(compiler, ContextCompilerProtocol)


# =====================================================================
# TraceClient Physical SQLite Tests
# =====================================================================


def test_trace_client_fts5_query_retrieval(tmp_path: Path) -> None:
    """Verify real SQLite FTS5 query retrieval with BM25 ranking and snippets."""
    db_file = tmp_path / "test_trace.db"
    client = _populate_test_trace_db(db_file)

    results = client.query_semantic_context(["reciprocal", "fusion"], max_results=3)
    assert len(results) >= 1
    assert "adr_concurrency.md" in results[0]
    assert "atom_001" in results[0]
    assert "<b>reciprocal</b>" in results[0] or "fusion" in results[0]

    # Non-matching keyword returns empty list
    empty_res = client.query_semantic_context(["nonexistenttermxyz"], max_results=3)
    assert empty_res == []


def test_trace_client_negative_inhibitor_retrieval(tmp_path: Path) -> None:
    """Verify negative inhibitor lookup from real proposals table."""
    db_file = tmp_path / "test_trace_inh.db"
    client = _populate_test_trace_db(db_file)

    inhibitors = client.query_negative_inhibitors("transport")
    assert len(inhibitors) >= 1
    assert any("named pipes" in inh for inh in inhibitors)

    all_inhs = client.query_negative_inhibitors("*")
    assert len(all_inhs) == 2


def test_trace_client_unattached_db_returns_empty(tmp_path: Path) -> None:
    """When DB file does not exist, TraceClient cleanly returns empty results (Neocortex-only)."""
    non_existent = tmp_path / "absent.db"
    client = TraceClient(db_path=non_existent)
    assert not client.has_live_db
    assert client.query_semantic_context(["keyword"]) == []
    assert client.query_negative_inhibitors("auth") == []


def test_trace_client_corrupted_query_raises_trace_memory_error(tmp_path: Path) -> None:
    """When a real SQLite error occurs, fail-closed TraceMemoryError is raised."""
    db_file = tmp_path / "corrupt.db"
    conn = sqlite3.connect(str(db_file))
    conn.execute("CREATE TABLE dummy (x TEXT);")
    conn.close()

    client = TraceClient(db_path=db_file)
    # lexical_fts table does not exist in this database
    import pytest

    with pytest.raises(TraceMemoryError):
        client.query_semantic_context(["keyword"])

    with pytest.raises(TraceMemoryError):
        client.query_negative_inhibitors("auth")


# =====================================================================
# ContextCompiler Compilation & Budget Gate Tests
# =====================================================================


def test_compile_sample_spec_within_budget() -> None:
    """Compiling bundle for sample_spec.md produces valid YAML measuring <= 25,600 bytes."""
    sample_path = Path("specs/sample_spec.md")
    assert sample_path.is_file()
    raw_content = sample_path.read_text(encoding="utf-8")
    atom = _create_spec_atom("sample_spec", raw_content)
    toc = _create_test_toc("sample_spec")

    compiler = ContextCompiler()
    bundle, byte_size, yaml_str = compiler.compile_bundle(
        task_id="TASK-SAMPLE-001",
        spec=atom,
        toc=toc,
        inhibitors=[],
    )

    assert isinstance(bundle, TaskBundle)
    assert bundle.task_id == "TASK-SAMPLE-001"
    assert byte_size <= 25600
    assert len(yaml_str.encode("utf-8")) == byte_size
    assert len(bundle.invariants) >= 3
    assert len(bundle.negative_inhibitors) >= 1
    assert len(bundle.target_files) >= 1


def test_compilation_latency_exit_gate() -> None:
    """Physical exit gate: compiling a bundle completes in < 200ms."""
    content = Path("specs/sample_spec.md").read_text(encoding="utf-8")
    atom = _create_spec_atom("latency_gate", content)
    toc = _create_test_toc("latency_gate")
    compiler = ContextCompiler()

    start = time.perf_counter()
    _bundle, byte_size, _yaml_str = compiler.compile_bundle(
        task_id="TASK-PERF-001",
        spec=atom,
        toc=toc,
        inhibitors=[],
    )
    duration_ms = (time.perf_counter() - start) * 1000.0

    assert byte_size <= 25600
    assert duration_ms < 200.0, f"Compilation took {duration_ms:.2f}ms (must be < 200ms)"


def test_negative_inhibitor_injection_from_trace_db(tmp_path: Path) -> None:
    """Verify past failure records from proposals appear in task_bundle.negative_inhibitors."""
    db_file = tmp_path / "trace_inh.db"
    trace_client = _populate_test_trace_db(db_file)

    content = "# Transport Service\nMust implement socket transport without deadlocks.\n"
    atom = _create_spec_atom("transport_service", content)
    toc = _create_test_toc("transport_service")

    compiler = ContextCompiler(trace_memory=trace_client)
    bundle = compiler.compile_task(
        task_id="TASK-INH-001",
        spec=atom,
        toc=toc,
        inhibitors=["Avoid sync blocking IO"],
    )

    assert "Avoid sync blocking IO" in bundle.negative_inhibitors
    assert any("named pipes" in inh for inh in bundle.negative_inhibitors)


def test_hierarchical_context_pruning_drops_episodic_traces_preserving_invariants(
    tmp_path: Path,
) -> None:
    """When injected traces exceed 25KB ceiling, compiler automatically drops low-ranking traces."""
    db_file = tmp_path / "prune_test.db"
    trace_client = TraceClient(db_path=db_file)
    trace_client.init_schema()

    trace_client.insert_document("doc_bulk", "bulk_traces.md")
    # Insert several large episodic traces (each ~15KB token)
    large_payload_1 = "reciprocal fusion memory " + ("A" * 15000)
    large_payload_2 = "reciprocal fusion memory " + ("B" * 15000)
    large_payload_3 = "reciprocal fusion memory " + ("C" * 15000)

    trace_client.insert_atom("atom_b1", "doc_bulk", large_payload_1)
    trace_client.insert_atom("atom_b2", "doc_bulk", large_payload_2)
    trace_client.insert_atom("atom_b3", "doc_bulk", large_payload_3)

    content = "# Fusion Service\nMust implement reciprocal fusion memory.\n"
    atom = _create_spec_atom("fusion_service", content)
    core_invariants = [
        "Invariant 1: Zero mock certification policy",
        "Invariant 2: Deterministic exit code 0 required",
        "Invariant 3: Cross-OS execution neutrality",
    ]
    toc = _create_test_toc("fusion_service", invariants=core_invariants)

    compiler = ContextCompiler(trace_memory=trace_client)
    bundle, byte_size, _yaml_str = compiler.compile_bundle(
        task_id="TASK-PRUNE-001",
        spec=atom,
        toc=toc,
        inhibitors=[],
    )

    # Must be strictly under 25,600 bytes
    assert byte_size <= 25600
    # Pruning was triggered
    assert compiler.last_pruned_traces_count > 0

    # Core Neocortex invariants MUST BE PRESERVED
    for inv in core_invariants:
        assert inv in bundle.invariants


def test_bundle_size_exceeded_error_on_non_prunable_overflow() -> None:
    """When Neocortex invariants alone exceed 25,600 bytes, fail-closed error is raised."""
    content = "# Massive Invariants Feature\n"
    atom = _create_spec_atom("massive_spec", content)
    # Create invariants that alone exceed 26KB
    massive_invariants = [f"Invariant {i}: " + ("X" * 1000) for i in range(30)]
    toc = _create_test_toc("massive_spec", invariants=massive_invariants)

    compiler = ContextCompiler()
    import pytest

    with pytest.raises(BundleSizeExceededError) as exc_info:
        compiler.compile_bundle(
            task_id="TASK-OVERFLOW-001",
            spec=atom,
            toc=toc,
            inhibitors=[],
        )
    assert "Context budget violated" in str(exc_info.value)
    assert "exceeds 25600 byte ceiling" in str(exc_info.value)


def test_save_bundle_writes_valid_yaml(tmp_path: Path) -> None:
    """Verify save_bundle writes valid YAML that deserializes back to TaskBundle."""
    atom = _create_spec_atom("save_test", "# Save Test Feature\nMust save properly.\n")
    toc = _create_test_toc("save_test")
    compiler = ContextCompiler()

    bundle = compiler.compile_task(
        task_id="TASK-SAVE-001",
        spec=atom,
        toc=toc,
        inhibitors=["No file leaks"],
        target_files=[FileTarget(path="src/stc/save.py", action="modify")],
        membrane_protocols=["SaveProtocol"],
    )

    out_file = tmp_path / "output" / "task_bundle.yaml"
    compiler.save_bundle(bundle, out_file)

    assert out_file.is_file()
    loaded_data = yaml.safe_load(out_file.read_text(encoding="utf-8"))
    rehydrated = TaskBundle.model_validate(loaded_data)
    assert rehydrated.task_id == bundle.task_id
    assert rehydrated.spec_id == bundle.spec_id
    assert rehydrated.target_files[0].path == "src/stc/save.py"


# =====================================================================
# CLI Integration Tests
# =====================================================================


def test_cli_compile_command_with_trace_db(tmp_path: Path) -> None:
    """stc compile with explicit --trace-db populates negative inhibitors."""
    db_file = tmp_path / "cli_trace.db"
    _populate_test_trace_db(db_file)

    spec_file = tmp_path / "cli_feature.md"
    spec_file.write_text(
        "# Transport Engine\nMust implement transport without deadlocks.\n",
        encoding="utf-8",
    )
    bundle_out = tmp_path / "artifacts" / "task_bundle.yaml"

    runner = CliRunner()
    res = runner.invoke(
        main,
        [
            "compile",
            "TASK-CLI-001",
            "--spec",
            str(spec_file),
            "--out",
            str(bundle_out),
            "--trace-db",
            str(db_file),
        ],
    )

    assert res.exit_code == 0
    assert "Bundle successfully compiled" in res.output
    assert bundle_out.is_file()

    data = yaml.safe_load(bundle_out.read_text(encoding="utf-8"))
    assert any("named pipes" in inh for inh in data["negative_inhibitors"])


def test_cli_compile_pruning_report(tmp_path: Path) -> None:
    """stc compile reports hierarchical context pruning when triggered."""
    db_file = tmp_path / "cli_prune.db"
    trace_client = TraceClient(db_path=db_file)
    trace_client.init_schema()

    trace_client.insert_document("doc_p", "prune_doc.md")
    trace_client.insert_atom("atom_p1", "doc_p", "engine transport " + ("Z" * 15000))
    trace_client.insert_atom("atom_p2", "doc_p", "engine transport " + ("W" * 15000))

    spec_file = tmp_path / "prune_spec.md"
    spec_file.write_text(
        "# Engine Transport\nMust handle bulk loads safely.\n",
        encoding="utf-8",
    )
    bundle_out = tmp_path / "pruned_bundle.yaml"

    runner = CliRunner()
    res = runner.invoke(
        main,
        [
            "compile",
            "TASK-PRUNE-CLI",
            "--spec",
            str(spec_file),
            "--out",
            str(bundle_out),
            "--trace-db",
            str(db_file),
        ],
    )

    assert res.exit_code == 0
    assert "Hierarchical context pruning triggered" in res.output
    assert "Pruned" in res.output
    assert bundle_out.is_file()


def test_cli_compile_json_mode(tmp_path: Path) -> None:
    """stc -j compile outputs valid JSON bundle to stdout."""
    spec_file = tmp_path / "json_spec.md"
    spec_file.write_text("# JSON Service\nMust output JSON.\n", encoding="utf-8")
    bundle_out = tmp_path / "bundle.yaml"

    runner = CliRunner()
    res = runner.invoke(
        main,
        ["-j", "compile", "TASK-JSON-001", "--spec", str(spec_file), "--out", str(bundle_out)],
    )

    assert res.exit_code == 0
    parsed = json.loads(res.output)
    assert parsed["task_id"] == "TASK-JSON-001"
    assert "invariants" in parsed
    assert "negative_inhibitors" in parsed
    assert bundle_out.is_file()


def test_trace_client_database_locked_raises_trace_memory_error(tmp_path: Path) -> None:
    """Verify that when an exclusive SQLite lock times out, TraceMemoryError is raised."""
    import pytest

    db_file = tmp_path / "locked.db"
    client = _populate_test_trace_db(db_file)
    client.timeout = 0.05

    # Hold exclusive lock in a separate connection
    locker = sqlite3.connect(str(db_file))
    locker.execute("BEGIN EXCLUSIVE;")
    try:
        with pytest.raises(TraceMemoryError):
            client.query_semantic_context(["reciprocal"], max_results=1)
        with pytest.raises(TraceMemoryError):
            client.query_negative_inhibitors("transport")
    finally:
        locker.rollback()
        locker.close()


def test_trace_client_proposals_without_component_column(tmp_path: Path) -> None:
    """Verify TraceClient handles standard schema without component column per spec §2.2."""
    db_file = tmp_path / "std_schema.db"
    conn = sqlite3.connect(str(db_file))
    conn.execute(
        """
        CREATE TABLE proposals (
            proposal_id TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            proposal_type TEXT NOT NULL,
            candidate_json TEXT DEFAULT '{}',
            decision_reason TEXT NOT NULL,
            created_event_id INTEGER DEFAULT 1
        );
        """
    )
    conn.execute(
        """
        INSERT INTO proposals (proposal_id, status, proposal_type, decision_reason)
        VALUES ('prop_01', 'REFUTED', 'negative_inhibitor', 'Avoid global state');
        """
    )
    conn.commit()
    conn.close()

    client = TraceClient(db_path=db_file)
    inhibitors = client.query_negative_inhibitors("*")
    assert len(inhibitors) == 1
    assert inhibitors[0] == "Avoid global state"


def test_trace_client_proposals_with_null_values(tmp_path: Path) -> None:
    """Verify proposal rows with NULL candidate_json or reason do not raise AttributeError."""
    db_file = tmp_path / "nulls.db"
    conn = sqlite3.connect(str(db_file))
    conn.execute(
        """
        CREATE TABLE proposals (
            proposal_id TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            proposal_type TEXT NOT NULL,
            candidate_json TEXT,
            decision_reason TEXT,
            component TEXT,
            created_event_id INTEGER DEFAULT 1
        );
        """
    )
    conn.execute(
        """
        INSERT INTO proposals
        (proposal_id, status, proposal_type, candidate_json, decision_reason, component)
        VALUES ('prop_null', 'REFUTED', 'negative_inhibitor', NULL, NULL, NULL);
        """
    )
    conn.commit()
    conn.close()

    client = TraceClient(db_path=db_file)
    inhibitors = client.query_negative_inhibitors("transport")
    assert inhibitors == []


def test_trace_client_fts5_leading_trailing_hyphens(tmp_path: Path) -> None:
    """Verify keywords with hyphens like '-deprecated' or '---' do not cause FTS5 syntax errors."""
    db_file = tmp_path / "hyphens.db"
    client = _populate_test_trace_db(db_file)

    res1 = client.query_semantic_context(["-reciprocal-"], max_results=3)
    assert len(res1) >= 1
    res2 = client.query_semantic_context(["---", "---foo---"], max_results=3)
    assert isinstance(res2, list)


def test_compiler_yaml_inflation_ceiling_enforced() -> None:
    """Ingested spec with characters that inflate in YAML is held strictly to the 25KB ceiling."""
    spec_content = "# Special Char Spec\n" + ("Special \u00a9 \u00ae \u2122 characters \n" * 50)
    atom = _create_spec_atom("special_spec", spec_content)
    toc = _create_test_toc("special_spec")

    compiler = ContextCompiler()
    _bundle, byte_size, yaml_str = compiler.compile_bundle(
        task_id="TASK-SPECIAL-001",
        spec=atom,
        toc=toc,
        inhibitors=[],
    )
    assert byte_size <= 25600
    assert len(yaml_str.encode("utf-8")) == byte_size


def test_compiler_negative_inhibitor_step_pruning(tmp_path: Path) -> None:
    """When episodic traces are absent/exhausted, negative inhibitors are pruned step-by-step."""
    atom = _create_spec_atom("inh_prune_spec", "# Inhibitor Prune Spec\n")
    # Invariants take ~20KB
    large_invariants = [f"Invariant {i}: " + ("I" * 500) for i in range(40)]
    toc = _create_test_toc("inh_prune_spec", invariants=large_invariants)

    # Inhibitors take ~10KB
    large_inhibitors = [f"Inhibitor {i}: " + ("X" * 1000) for i in range(10)]

    compiler = ContextCompiler()
    bundle, byte_size, _yaml_str = compiler.compile_bundle(
        task_id="TASK-INH-PRUNE-001",
        spec=atom,
        toc=toc,
        inhibitors=large_inhibitors,
    )
    assert byte_size <= 25600
    assert compiler.last_pruned_inhibitors_count > 0
    # Neocortex invariants were fully preserved
    assert len(bundle.invariants) == len(large_invariants)


def test_compiler_coverage_and_latency_tracking(tmp_path: Path) -> None:
    """Verify hippocampal_coverage and query latency are tracked per DAG N07."""
    db_file = tmp_path / "coverage.db"
    trace_client = _populate_test_trace_db(db_file)

    atom = _create_spec_atom("coverage_spec", "# Reciprocal Engine\n")
    toc = _create_test_toc("coverage_spec")

    compiler = ContextCompiler(trace_memory=trace_client)
    _bundle = compiler.compile_task(
        task_id="TASK-COV-001",
        spec=atom,
        toc=toc,
        inhibitors=[],
    )
    assert compiler.hippocampal_coverage is True
    assert compiler.hippocampal_query_latency_ms >= 0.0

    # Without trace_memory (Neocortex-only)
    compiler_no_db = ContextCompiler(trace_memory=None)
    _bundle_no_db = compiler_no_db.compile_task(
        task_id="TASK-COV-002",
        spec=atom,
        toc=toc,
        inhibitors=[],
    )
    assert compiler_no_db.hippocampal_coverage is False


def test_cli_compile_trace_memory_error_exit_code(tmp_path: Path) -> None:
    """Corrupt trace DB causes stc compile to exit with non-zero exit code and clean error."""
    corrupt_db = tmp_path / "corrupt.db"
    corrupt_db.write_bytes(b"NOT A VALID SQLITE DB")

    spec_file = tmp_path / "corrupt_spec.md"
    spec_file.write_text("# Corrupt Spec\nValid content for testing.\n", encoding="utf-8")
    bundle_out = tmp_path / "bundle.yaml"

    runner = CliRunner()
    res = runner.invoke(
        main,
        [
            "compile",
            "TASK-CORRUPT-001",
            "--spec",
            str(spec_file),
            "--out",
            str(bundle_out),
            "--trace-db",
            str(corrupt_db),
        ],
    )
    assert res.exit_code != 0
    assert "Trace" in res.output or "database" in res.output


def test_trace_client_init_schema_and_table_structure(tmp_path: Path) -> None:
    """Verify TraceClient table initialization, insert methods, and default column values."""
    db_file = tmp_path / "sub" / "schema_test.db"
    client = TraceClient(db_path=db_file, timeout=4.0)
    assert client.timeout == 4.0
    client.init_schema()
    assert db_file.is_file()

    conn = sqlite3.connect(str(db_file))
    cur = conn.cursor()
    tables = {
        r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }
    assert {"documents", "atoms", "lexical_fts", "proposals", "events", "attachments"}.issubset(
        tables
    )

    # Test insert_document default collection and custom collection
    client.insert_document("d1", "doc1.md")
    client.insert_document("d2", "doc2.md", collection="custom_coll")
    doc_rows = cur.execute(
        "SELECT document_id, document_name, collection FROM documents ORDER BY document_id"
    ).fetchall()
    assert doc_rows == [("d1", "doc1.md", "default"), ("d2", "doc2.md", "custom_coll")]

    # Test insert_atom into atoms and lexical_fts
    client.insert_atom("a1", "d1", "First atom content with keyword alpha.")
    client.insert_atom("a2", "d2", "Second atom content with keyword beta.")
    atom_rows = cur.execute(
        "SELECT atom_id, document_id, content FROM atoms ORDER BY atom_id"
    ).fetchall()
    assert atom_rows == [
        ("a1", "d1", "First atom content with keyword alpha."),
        ("a2", "d2", "Second atom content with keyword beta."),
    ]
    fts_rows = cur.execute("SELECT atom_id, content FROM lexical_fts ORDER BY atom_id").fetchall()
    assert fts_rows == [
        ("a1", "First atom content with keyword alpha."),
        ("a2", "Second atom content with keyword beta."),
    ]

    # Test insert_proposal with defaults and custom fields
    client.insert_proposal("p1", "REFUTED", "negative_inhibitor", "Do not use threads")
    client.insert_proposal(
        proposal_id="p2",
        status="REJECTED",
        proposal_type="negative_inhibitor",
        decision_reason="Avoid locks",
        candidate_json='{"opt": 1}',
        component="core",
        created_event_id=42,
    )
    prop_rows = cur.execute(
        "SELECT proposal_id, status, proposal_type, candidate_json, "
        "decision_reason, component, created_event_id FROM proposals ORDER BY proposal_id"
    ).fetchall()
    assert prop_rows == [
        ("p1", "REFUTED", "negative_inhibitor", "{}", "Do not use threads", "", 1),
        ("p2", "REJECTED", "negative_inhibitor", '{"opt": 1}', "Avoid locks", "core", 42),
    ]
    conn.close()


def test_trace_client_query_semantic_context_details(tmp_path: Path) -> None:
    """Verify query_semantic_context token sanitation, formatting, and max_results clamping."""
    db_file = tmp_path / "semantic_details.db"
    client = TraceClient(db_path=db_file)
    client.init_schema()
    client.insert_document("d1", "arch.md")
    client.insert_atom("a1", "d1", "Distributed consensus using raft algorithm")

    # Punctuation / whitespace cleaning
    res = client.query_semantic_context(["  consensus!!  ", "--raft--", ""], max_results=2)
    assert len(res) == 1
    assert "[arch.md:a1]" in res[0]
    assert "consensus" in res[0] or "raft" in res[0]

    # Empty token list after cleaning
    assert client.query_semantic_context(["---", "!!!", ""]) == []
    assert client.query_semantic_context([]) == []

    # max_results < 1 clamped to 1
    res_clamped = client.query_semantic_context(["consensus"], max_results=0)
    assert len(res_clamped) == 1


def test_trace_client_query_negative_inhibitors_matching_logic(tmp_path: Path) -> None:
    """Verify query_negative_inhibitors multi-branch matching, wildcard, and result capping."""
    db_file = tmp_path / "inhibitors_logic.db"
    client = TraceClient(db_path=db_file)
    client.init_schema()

    # Insert 6 inhibitors to test capping at 5
    for i in range(1, 7):
        client.insert_proposal(
            proposal_id=f"p_comp_{i}",
            status="REFUTED",
            proposal_type="negative_inhibitor",
            decision_reason=f"Reason {i} for memory failure",
            component="memory",
            created_event_id=i,
        )

    client.insert_proposal(
        proposal_id="p_json",
        status="REJECTED",
        proposal_type="negative_inhibitor",
        decision_reason="Reason json match",
        candidate_json='{"component": "network_layer"}',
        component="other",
        created_event_id=10,
    )

    client.insert_proposal(
        proposal_id="p_reason",
        status="QUARANTINED",
        proposal_type="negative_inhibitor",
        decision_reason="Avoid filesystem corruption here",
        component="other",
        created_event_id=11,
    )

    # Empty reason row should be skipped
    client.insert_proposal(
        proposal_id="p_empty_reason",
        status="REFUTED",
        proposal_type="negative_inhibitor",
        decision_reason="   ",
        component="memory",
        created_event_id=12,
    )

    # Test cap at 5: querying "memory" matches 6 rows, should cap at 5
    mem_inhs = client.query_negative_inhibitors("memory")
    assert len(mem_inhs) == 5

    # Test wildcard "*" returns up to 5
    all_inhs = client.query_negative_inhibitors("*")
    assert len(all_inhs) == 5

    # Test empty string returns up to 5
    empty_inhs = client.query_negative_inhibitors("   ")
    assert len(empty_inhs) == 5

    # Test candidate_json match
    json_inhs = client.query_negative_inhibitors("network_layer")
    assert json_inhs == ["Reason json match"]

    # Test reason substring match
    fs_inhs = client.query_negative_inhibitors("filesystem")
    assert fs_inhs == ["Avoid filesystem corruption here"]

    # Non-matching component
    assert client.query_negative_inhibitors("nonexistent_subsystem") == []


def test_context_compiler_extract_keywords_exhaustive() -> None:
    """Verify _extract_keywords filters stopwords, extracts from all TOC dimensions, caps at 10."""
    stopwords = [
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
    ]
    # Verify stopwords are NOT in keywords
    toc_stop = _create_test_toc("spec", invariants=["must never"])
    goal_stop = (
        "the and for with that this from are was were will should could have "
        "has had not but into over after"
    )
    kw_stop = ContextCompiler._extract_keywords("spec", goal_stop, toc_stop)
    for sw in stopwords:
        assert sw not in kw_stop, f"Stopword '{sw}' was not filtered"

    # Verify terms from all 5 dimensions are extracted
    toc = TreeOfConcerns(
        spec_id="dim_test",
        domain_invariants=ConcernDimension(
            dimension_name="domain_invariants",
            invariants=["alpha"],
        ),
        persistence_storage=ConcernDimension(
            dimension_name="persistence_storage",
            contracts=["beta"],
        ),
        communication_protocols=ConcernDimension(
            dimension_name="communication_protocols",
            contracts=["gamma"],
        ),
        boundary_security=ConcernDimension(
            dimension_name="boundary_security",
            contracts=["delta"],
        ),
        failure_resilience=ConcernDimension(
            dimension_name="failure_resilience",
            failure_modes=["epsilon"],
        ),
        ambiguity_score=0.0,
    )
    keywords = ContextCompiler._extract_keywords("sub-module", "run", toc)
    assert keywords == ["sub", "module", "run", "alpha", "beta", "gamma", "delta", "epsilon"]

    # Length < 3 should be omitted
    toc_short = TreeOfConcerns(
        spec_id="ab",
        domain_invariants=ConcernDimension(
            dimension_name="domain_invariants",
            invariants=["cd ef"],
        ),
        persistence_storage=ConcernDimension(dimension_name="persistence_storage"),
        communication_protocols=ConcernDimension(dimension_name="communication_protocols"),
        boundary_security=ConcernDimension(dimension_name="boundary_security"),
        failure_resilience=ConcernDimension(dimension_name="failure_resilience"),
        ambiguity_score=0.0,
    )
    assert ContextCompiler._extract_keywords("ab", "cd", toc_short) == []

    # Exactly 3 characters included
    toc_three = TreeOfConcerns(
        spec_id="abc",
        domain_invariants=ConcernDimension(dimension_name="domain_invariants", invariants=["def"]),
        persistence_storage=ConcernDimension(dimension_name="persistence_storage"),
        communication_protocols=ConcernDimension(dimension_name="communication_protocols"),
        boundary_security=ConcernDimension(dimension_name="boundary_security"),
        failure_resilience=ConcernDimension(dimension_name="failure_resilience"),
        ambiguity_score=0.0,
    )
    assert ContextCompiler._extract_keywords("abc", "ghi", toc_three) == ["abc", "ghi", "def"]

    # Deduplication and cap at 10
    toc_many = TreeOfConcerns(
        spec_id="wordone",
        domain_invariants=ConcernDimension(
            dimension_name="domain_invariants",
            invariants=[
                "wordtwo wordthree wordfour wordfive wordsix",
                "wordseven wordeight wordnine wordten wordeleven wordtwelve",
            ],
        ),
        persistence_storage=ConcernDimension(dimension_name="persistence_storage"),
        communication_protocols=ConcernDimension(dimension_name="communication_protocols"),
        boundary_security=ConcernDimension(dimension_name="boundary_security"),
        failure_resilience=ConcernDimension(dimension_name="failure_resilience"),
        ambiguity_score=0.0,
    )
    kw_many = ContextCompiler._extract_keywords("wordone", "wordone", toc_many)
    assert len(kw_many) == 10
    assert kw_many == [
        "wordone",
        "wordtwo",
        "wordthree",
        "wordfour",
        "wordfive",
        "wordsix",
        "wordseven",
        "wordeight",
        "wordnine",
        "wordten",
    ]


def test_context_compiler_extract_spec_metadata_exhaustive() -> None:
    """Verify _extract_spec_metadata file extraction, protocol parsing, and rules."""
    toc = TreeOfConcerns(
        spec_id="spec_meta",
        domain_invariants=ConcernDimension(dimension_name="domain_invariants", invariants=[]),
        persistence_storage=ConcernDimension(dimension_name="persistence_storage"),
        communication_protocols=ConcernDimension(
            dimension_name="communication_protocols",
            contracts=["Must implement MembraneAuditProtocol here."],
        ),
        boundary_security=ConcernDimension(dimension_name="boundary_security"),
        failure_resilience=ConcernDimension(dimension_name="failure_resilience"),
        ambiguity_score=0.0,
    )

    raw_spec = (
        "# System Specification\n"
        "Modify files `src/stc/engine.py` and 'code/utilities.py' and \"tests/test_flow.py\".\n"
        "Also reference non-quoted src/stc/other_service.py in text.\n"
        "Windows path with backslash: src\\stc\\win_path.py.\n"
        "Duplicate path `src/stc/engine.py`.\n"
        "Protocol used: WorkerProtocol and JudiciaryProtocol.\n"
        "Line with rule: Rule 1: All operations must succeed.\n"
        "Line with must: Account balance must never fall.\n"
        "Line with never: System will never leak secrets.\n"
        "Line with invariant: Core invariant: strict monotonicity.\n"
        "Short: must\n"
        "Line with inhibitor: Active inhibitor: do not block the thread.\n"
        "Line with refuted: Architecture refuted: sync sockets.\n"
        "Line with avoid: Strongly avoid global mutable maps.\n"
        "Line with do not: Please do not catch bare exceptions.\n"
        "Short inhibitor: avoid\n"
    )

    files, protocols, invariants, inhibitors = ContextCompiler._extract_spec_metadata(
        raw_spec, "spec_meta", toc
    )

    file_paths = [f.path for f in files]
    assert "src/stc/engine.py" in file_paths
    assert "code/utilities.py" in file_paths
    assert "tests/test_flow.py" in file_paths
    assert "src/stc/other_service.py" in file_paths
    assert "src/stc/win_path.py" in file_paths
    assert file_paths.count("src/stc/engine.py") == 1
    assert all(f.action == "modify" for f in files)

    # Protocols from raw_content and toc
    assert protocols == ["JudiciaryProtocol", "MembraneAuditProtocol", "WorkerProtocol"]

    # Invariants
    assert any("All operations must succeed" in inv for inv in invariants)
    assert any("Account balance must never fall" in inv for inv in invariants)
    assert any("System will never leak secrets" in inv for inv in invariants)
    assert any("Core invariant: strict monotonicity" in inv for inv in invariants)
    assert "must" not in invariants

    # Inhibitors
    assert any("Active inhibitor: do not block" in inh for inh in inhibitors)
    assert any("Architecture refuted: sync sockets" in inh for inh in inhibitors)
    assert any("Strongly avoid global mutable maps" in inh for inh in inhibitors)
    assert any("Please do not catch bare exceptions" in inh for inh in inhibitors)
    assert "avoid" not in inhibitors


def test_context_compiler_defaults_and_metadata_preservation() -> None:
    """Verify ContextCompiler default fallbacks, correlation generation, and task compilation."""
    compiler = ContextCompiler(max_bundle_bytes=20000)
    assert compiler.max_bundle_bytes == 20000
    assert compiler.last_pruned_traces_count == 0
    assert compiler.last_pruned_inhibitors_count == 0
    assert compiler.initial_bundle_bytes == 0
    assert compiler.last_bundle_bytes == 0
    assert compiler.hippocampal_coverage is False
    assert compiler.hippocampal_query_latency_ms == 0.0

    atom = _create_spec_atom("spec_blank", "A brief overview without code paths.")
    toc = TreeOfConcerns(
        spec_id="spec_blank",
        domain_invariants=ConcernDimension(dimension_name="domain_invariants", invariants=[]),
        persistence_storage=ConcernDimension(dimension_name="persistence_storage"),
        communication_protocols=ConcernDimension(dimension_name="communication_protocols"),
        boundary_security=ConcernDimension(dimension_name="boundary_security"),
        failure_resilience=ConcernDimension(dimension_name="failure_resilience"),
        ambiguity_score=0.0,
    )

    bundle, byte_size, _yaml_str = compiler.compile_bundle(
        task_id="TASK-DEF-001",
        spec=atom,
        toc=toc,
        inhibitors=[],
        epoch_index=2,
        correlation_id="corr_custom_1234",
        causation_id="cause_parent_5678",
    )

    assert bundle.epoch_index == 2
    assert bundle.correlation_id == "corr_custom_1234"
    assert bundle.causation_id == "cause_parent_5678"
    assert bundle.invariants == [
        "Zero mock certification policy",
        "Deterministic exit code 0 required",
        "Cross-OS execution neutrality",
    ]
    assert bundle.target_files[0].path == "src/stc/spec_blank.py"
    assert bundle.membrane_protocols == ["SubstrateRunnerProtocol", "HormoneBusProtocol"]
    assert bundle.negative_inhibitors == [
        "Do not use mock assertions in verification tests",
        "Do not run native mutmut on Windows without WSL",
    ]
    assert compiler.initial_bundle_bytes == byte_size
    assert compiler.last_bundle_bytes == byte_size
    assert compiler.hippocampal_coverage is False

    # Test compile_task wrapper
    task_res = compiler.compile_task(
        task_id="TASK-DEF-002",
        spec=atom,
        toc=toc,
        inhibitors=[],
        correlation_id="corr_task_123456",
    )
    assert isinstance(task_res, TaskBundle)
    assert task_res.task_id == "TASK-DEF-002"
    assert task_res.correlation_id == "corr_task_123456"

    # Test auto-generated correlation_id
    auto_bundle, _, _ = compiler.compile_bundle(
        task_id="TASK-AUTO-001",
        spec=atom,
        toc=toc,
        inhibitors=[],
    )
    assert auto_bundle.correlation_id.startswith("corr_")
    assert len(auto_bundle.correlation_id) >= 15
    assert auto_bundle.causation_id is None

    # Test to_yaml method
    yaml_text = ContextCompiler.to_yaml(auto_bundle)
    assert "TASK-AUTO-001" in yaml_text
    assert isinstance(yaml_text, str)


def test_save_bundle_deep_directory_and_overwrite(tmp_path: Path) -> None:
    """Verify save_bundle handles deeply nested parents, idempotency, and return path."""
    atom = _create_spec_atom("spec_save", "Save test.")
    toc = _create_test_toc("spec_save")
    compiler = ContextCompiler()
    bundle = compiler.compile_task("TASK-SV-01", atom, toc, inhibitors=[])

    # Deep directory test (verifies mkdir parents=True)
    deep_path = tmp_path / "deep" / "nested" / "output" / "task_bundle.yaml"
    ret_path = compiler.save_bundle(bundle, deep_path)
    assert ret_path == deep_path
    assert deep_path.is_file()

    # Overwrite test on existing directory (verifies mkdir exist_ok=True)
    compiler.save_bundle(bundle, deep_path)
    assert deep_path.is_file()


def test_compile_task_argument_forwarding() -> None:
    """Verify compile_task forwards epoch_index, membrane_protocols, and causation_id."""
    atom = _create_spec_atom("spec_fwd", "Forwarding test.")
    toc = _create_test_toc("spec_fwd")
    compiler = ContextCompiler()

    # Default epoch_index must be 1
    default_res = compiler.compile_task("TASK-FWD-01", atom, toc, inhibitors=[])
    assert default_res.epoch_index == 1

    # Custom membrane_protocols, causation_id, epoch_index
    custom_res = compiler.compile_task(
        "TASK-FWD-02",
        atom,
        toc,
        inhibitors=[],
        epoch_index=3,
        membrane_protocols=["MembraneGatewayProtocol"],
        causation_id="cause_upstream_event",
    )
    assert custom_res.epoch_index == 3
    assert custom_res.membrane_protocols == ["MembraneGatewayProtocol"]
    assert custom_res.causation_id == "cause_upstream_event"


def test_to_yaml_canonical_formatting() -> None:
    """Verify to_yaml keeps insertion order (sort_keys=False) and serializes faithfully."""
    atom = _create_spec_atom("spec_fmt", "Format test.")
    toc = _create_test_toc("spec_fmt")
    compiler = ContextCompiler()
    bundle = compiler.compile_task("TASK-FMT-01", atom, toc, inhibitors=[])

    yaml_output = ContextCompiler.to_yaml(bundle)
    lines = yaml_output.strip().splitlines()
    assert lines[0].startswith("task_id:"), f"Expected task_id first, got: {lines[0]}"

    parsed = yaml.safe_load(yaml_output)
    rehydrated = TaskBundle.model_validate(parsed)
    assert rehydrated.task_id == "TASK-FMT-01"


def test_extract_spec_metadata_edge_cases() -> None:
    """Verify exact length boundaries (>5 and <=100) and stripping in _extract_spec_metadata."""
    toc = _create_test_toc("spec_bounds")
    long_line = "Must " + ("y" * 120)
    spec_text = f"### - * Must stripped correctly\nMust5\nMust 6\n{long_line}\nAvoid5\nDo not 6\n"
    _files, _protocols, invariants, inhibitors = ContextCompiler._extract_spec_metadata(
        spec_text, "spec_bounds", toc
    )
    assert any("Must stripped correctly" in inv for inv in invariants)
    assert "Must5" not in invariants
    assert any("Must 6" in inv for inv in invariants)
    long_invs = [inv for inv in invariants if inv.startswith("Must y")]
    assert len(long_invs) == 1
    assert len(long_invs[0]) == 100
    assert any("Do not 6" in inh for inh in inhibitors)


def test_compile_bundle_hippocampal_coverage_cases(tmp_path: Path) -> None:
    """Verify hippocampal_coverage boolean logic and exact correlation_id length."""
    db_file = tmp_path / "cov_cases.db"
    trace_client = TraceClient(db_path=db_file)
    trace_client.init_schema()
    trace_client.insert_document("d1", "test.md")
    trace_client.insert_atom("a1", "d1", "Network service semantic memory match atom")

    atom = _create_spec_atom("network_service", "Network service specification.")
    toc = _create_test_toc("network_service")

    compiler = ContextCompiler(trace_memory=trace_client)
    bundle, _, _ = compiler.compile_bundle("TASK-COV-A", atom, toc, inhibitors=[])
    assert compiler.hippocampal_coverage is True
    assert len(bundle.correlation_id) == 17

    trace_client.insert_proposal(
        proposal_id="p_wild",
        status="REFUTED",
        proposal_type="negative_inhibitor",
        decision_reason="Wildcard inhibitor for all tasks",
        component="*",
    )
    trace_client.insert_proposal(
        proposal_id="p_net",
        status="REFUTED",
        proposal_type="negative_inhibitor",
        decision_reason="Network inhibitor from spec prefix",
        component="network",
    )
    compiler_b = ContextCompiler(trace_memory=trace_client)
    bundle_b, _, _ = compiler_b.compile_bundle("TASK-COV-B", atom, toc, inhibitors=[])
    assert any("Wildcard inhibitor" in inh for inh in bundle_b.negative_inhibitors)
    assert any("Network inhibitor" in inh for inh in bundle_b.negative_inhibitors)


def test_pruning_step_increments(tmp_path: Path) -> None:
    """Verify multi-step pruning increments counters accurately (+= 1 per step)."""
    db_file = tmp_path / "prune_steps.db"
    trace_client = TraceClient(db_path=db_file)
    trace_client.init_schema()
    trace_client.insert_document("d_step", "steps.md")
    trace_client.insert_atom("t1", "d_step", "step atom " + ("1" * 10000))
    trace_client.insert_atom("t2", "d_step", "step atom " + ("2" * 10000))
    trace_client.insert_atom("t3", "d_step", "step atom " + ("3" * 10000))

    atom = _create_spec_atom("step_spec", "# Step Spec\nMust prune step by step.\n")
    toc = _create_test_toc("step_spec")

    compiler = ContextCompiler(trace_memory=trace_client, max_bundle_bytes=15000)
    _bundle, byte_size, _ = compiler.compile_bundle("TASK-STEP-01", atom, toc, inhibitors=[])
    assert byte_size <= 15000
    assert compiler.last_pruned_traces_count >= 2


def test_trace_client_default_timeout_and_replace(tmp_path: Path) -> None:
    """Verify TraceClient default timeout is 5.0 and replace semantics on insert_document."""
    default_client = TraceClient()
    assert default_client.timeout == 5.0

    db_file = tmp_path / "replace.db"
    client = TraceClient(db_path=db_file)
    client.init_schema()

    client.insert_document("d_rep", "old_name.md", collection="v1")
    client.insert_document("d_rep", "new_name.md", collection="v2")
    conn = sqlite3.connect(str(db_file))
    cur = conn.cursor()
    row = cur.execute(
        "SELECT document_name, collection FROM documents WHERE document_id='d_rep'"
    ).fetchone()
    assert row == ("new_name.md", "v2")
    conn.close()


def test_trace_client_auto_init_on_insert(tmp_path: Path) -> None:
    """Verify unattached TraceClient auto-initializes schema on first write."""
    auto_db = tmp_path / "auto_init.db"
    client = TraceClient(db_path=auto_db)
    assert not auto_db.is_file()
    client.insert_document("d1", "test.md")
    assert auto_db.is_file()
    assert client.has_live_db
    client.insert_atom("a1", "d1", "content")
    client.insert_proposal("p1", "REFUTED", "negative_inhibitor", "reason", component="comp")
    assert len(client.query_semantic_context(["content"])) == 1
    assert len(client.query_negative_inhibitors("comp")) == 1


def test_trace_client_init_schema_deep_parents(tmp_path: Path) -> None:
    """Verify init_schema creates deeply nested parent directories (parents=True)."""
    deep_path = tmp_path / "deep" / "nested" / "dir" / "trace.db"
    assert not deep_path.parent.exists()
    client = TraceClient(db_path=deep_path)
    client.init_schema()
    assert deep_path.parent.is_dir()
    assert deep_path.is_file()


def test_trace_client_query_semantic_context_options(tmp_path: Path) -> None:
    """Verify query_semantic_context default max_results=3, token cleaning, and null handling."""
    db_file = tmp_path / "semantic_opts.db"
    client = TraceClient(db_path=db_file)
    client.init_schema()
    client.insert_document("doc1", "test_doc.md")
    for i in range(5):
        client.insert_atom(f"atom_{i}", "doc1", f"database connection pooling benchmark sample {i}")

    # 1. Default max_results is 3
    res_default = client.query_semantic_context(["database", "pooling"])
    assert len(res_default) == 3

    # 2. Explicit max_results=1
    res_one = client.query_semantic_context(["database", "pooling"], max_results=1)
    assert len(res_one) == 1

    # 3. Special characters and leading/trailing hyphens cleaned
    res_clean = client.query_semantic_context(["@database#", "--pooling--", "-", "---"])
    assert len(res_clean) >= 1

    # 4. Null / empty field formatting: insert row with empty atom_id and doc_name
    conn = sqlite3.connect(str(db_file))
    conn.execute("INSERT INTO documents (document_id, document_name) VALUES ('d_empty', '')")
    conn.execute(
        "INSERT INTO atoms (atom_id, document_id, content) "
        "VALUES ('', 'd_empty', 'isolated snippet text')"
    )
    conn.execute("INSERT INTO lexical_fts (atom_id, content) VALUES ('', 'isolated snippet text')")
    conn.commit()
    conn.close()

    res_empty = client.query_semantic_context(["isolated", "snippet"])
    assert len(res_empty) >= 1
    assert res_empty[0].startswith("[:] ")
    assert "isolated" in res_empty[0]
    assert "XXXX" not in res_empty[0]


def test_trace_client_query_negative_inhibitors_exact_matching(tmp_path: Path) -> None:
    """Verify query_negative_inhibitors case insensitivity, trimming, and null handling."""
    db_file = tmp_path / "inhibitor_matching.db"
    client = TraceClient(db_path=db_file)
    client.init_schema()

    # Mixed case component
    client.insert_proposal(
        proposal_id="p_mixed",
        status="REFUTED",
        proposal_type="negative_inhibitor",
        decision_reason="  trimmed whitespace reason  ",
        component="Mixed_Case_Component",
    )
    # Proposal with wildcard component
    client.insert_proposal(
        proposal_id="p_wild",
        status="REFUTED",
        proposal_type="negative_inhibitor",
        decision_reason="Wildcard rule applies everywhere",
        component="*",
    )

    # 1. Case-insensitive component match and reason whitespace trimming
    res = client.query_negative_inhibitors("mixed_case_component")
    assert any("trimmed whitespace reason" in r and not r.startswith("  ") for r in res)
    assert "XXXX" not in "".join(res)

    # 2. Wildcard component match (target_comp == '*')
    res_wild = client.query_negative_inhibitors("*")
    assert any("Wildcard rule applies everywhere" in r for r in res_wild)

    # 3. Component None / null does not match bogus string like 'XXXX'
    conn = sqlite3.connect(str(db_file))
    conn.execute(
        "INSERT INTO proposals (proposal_id, status, proposal_type, decision_reason, component) "
        "VALUES ('p_null', 'REFUTED', 'negative_inhibitor', 'Null comp reason', NULL)"
    )
    conn.commit()
    conn.close()
    res_null = client.query_negative_inhibitors("XXXX")
    assert not any("Null comp reason" in r for r in res_null)


def test_context_compiler_targeted_mutation_coverage(tmp_path: Path) -> None:
    """Verify compile_bundle defaults, keyword filtering, fallback paths, and slicing."""
    compiler_no_mem = ContextCompiler(trace_memory=None)
    assert compiler_no_mem.hippocampal_query_latency_ms == 0.0

    # 1. Spec with hyphens and no file paths -> fallback path replaces hyphen with underscore
    atom_hyphen = _create_spec_atom(
        "storage-engine-driver", "# Storage Engine\nImplementation detail."
    )
    toc_hyphen = _create_test_toc("storage-engine-driver")
    bundle_h, _, _ = compiler_no_mem.compile_bundle(
        "TASK-H-01", atom_hyphen, toc_hyphen, inhibitors=[]
    )
    assert bundle_h.target_files[0].path == "src/stc/storage_engine_driver.py"
    assert bundle_h.epoch_index == 1
    assert compiler_no_mem.last_pruned_inhibitors_count == 0

    # 2. Spec with >5 files and >5 protocols -> clamped to exactly 5
    spec_with_many = (
        "# Multi File Spec\n"
        "`src/stc/f1.py`\n`src/stc/f2.py`\n`src/stc/f3.py`\n"
        "`src/stc/f4.py`\n`src/stc/f5.py`\n`src/stc/f6.py`\n"
        "Must use P1Protocol, P2Protocol, P3Protocol, P4Protocol, P5Protocol, P6Protocol.\n"
        "The rule is strict determinism.\n"
        "Negative inhibitor avoids memory leak.\n"
        "avoid\n"
        "avoid!\n"
        "Must " + ("z" * 120) + "\n"
    )
    atom_many = _create_spec_atom("multi_spec", spec_with_many)
    toc_many = _create_test_toc("multi_spec")
    bundle_m, _, _ = compiler_no_mem.compile_bundle(
        "TASK-M-01", atom_many, toc_many, inhibitors=["", "   "]
    )
    assert len(bundle_m.target_files) == 5
    assert len(bundle_m.membrane_protocols) == 5
    # Empty inhibitors filtered out
    assert "" not in bundle_m.negative_inhibitors
    assert "   " not in bundle_m.negative_inhibitors
    # Rule keyword extracted
    assert any("rule is strict determinism" in inv for inv in bundle_m.invariants)
    # Inhibitor keyword extracted
    assert any("inhibitor avoids memory leak" in inh for inh in bundle_m.negative_inhibitors)
    # Length boundaries for inhibitor: avoid (len 5) vs avoid! (len 6)
    assert not any(inh == "avoid" for inh in bundle_m.negative_inhibitors)
    assert any("avoid!" in inh for inh in bundle_m.negative_inhibitors)
    # 100 character truncation
    z_invs = [inv for inv in bundle_m.invariants if "zzz" in inv]
    assert len(z_invs) == 1
    assert len(z_invs[0]) == 100

    # 3. Stopwords 'test' and 'feature' filtered out in _extract_keywords
    keywords = ContextCompiler._extract_keywords("test_feature_spec", "Test feature goal", toc_many)
    assert "test" not in keywords
    assert "feature" not in keywords

    # 4. Heading stripping without '#' and spec relative path stripping './'
    spec_with_headings = (
        "## Implementation Architecture\nArchitecture details.\n./src/stc/relative_target.py\n"
    )
    files, _protos, _invs, _inhs = ContextCompiler._extract_spec_metadata(
        spec_with_headings, "arch_spec", toc_many
    )
    assert any(f.path == "src/stc/relative_target.py" for f in files)
    assert not any(f.path.startswith("./") for f in files)

    # 5. Semantic context querying max_results=3 limit in compile_bundle
    db_file = tmp_path / "bundle_limits.db"
    trace_client = TraceClient(db_path=db_file)
    trace_client.init_schema()
    trace_client.insert_document("d_lim", "limit.md")
    for i in range(5):
        trace_client.insert_atom(f"atom_lim_{i}", "d_lim", f"architecture details atom {i}")

    # Insert proposal for component matching prefix
    trace_client.insert_proposal(
        proposal_id="p_arch",
        status="REFUTED",
        proposal_type="negative_inhibitor",
        decision_reason="Architecture inhibitor component match",
        component="arch",
    )

    compiler_mem = ContextCompiler(trace_memory=trace_client)
    atom_arch = _create_spec_atom("arch_spec", spec_with_headings)
    bundle_arch, _, _ = compiler_mem.compile_bundle(
        "TASK-ARCH-01", atom_arch, toc_many, inhibitors=[]
    )
    trace_invs = [inv for inv in bundle_arch.invariants if inv.startswith("[Trace]")]
    assert len(trace_invs) == 3
    assert compiler_mem.hippocampal_query_latency_ms > 0.0
    assert any(
        "Architecture inhibitor component match" in inh for inh in bundle_arch.negative_inhibitors
    )
