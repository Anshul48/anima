"""Unit tests for the P02 file-backed memory shim.

Verifies packet acceptance against both the shipped corpus and fixture
corpora: protocol conformance, no-hallucination ([] on unknown), match-all
parity with TraceClient semantics, citation-first + as-of stamps on every
output, stale-flag rendering, and bundler-consumer wiring.
"""

from __future__ import annotations

import hashlib
import inspect
import re
from pathlib import Path

from stc.compiler.bundler import ContextCompiler
from stc.core.errors import TraceMemoryError
from stc.integration.memory import FileBackedMemory
from stc.memory.trace_client import TraceClient
from stc.protocols.interfaces import TraceMemoryProtocol
from stc.schemas.models import ConcernDimension, SpecAtom, TreeOfConcerns

STAMP_RE = re.compile(r"\(as-of [A-Z-]*@[0-9a-f]{40}, \d{4}-\d{2}-\d{2}\)")

FAKE_SHA = "a" * 40


def _spec_atom(spec_id: str, content: str) -> SpecAtom:
    return SpecAtom(
        spec_id=spec_id,
        source_path=f"specs/{spec_id}.md",
        raw_content=content,
        content_sha256=hashlib.sha256(content.encode("utf-8")).hexdigest(),
    )


def _toc() -> TreeOfConcerns:
    return TreeOfConcerns(
        spec_id="mem-probe",
        domain_invariants=ConcernDimension(
            dimension_name="domain_invariants",
            invariants=["Custody gates must be explicit.", "Zero mock certification policy."],
        ),
        persistence_storage=ConcernDimension(
            dimension_name="persistence_storage", contracts=["SQLite session tables."]
        ),
        communication_protocols=ConcernDimension(
            dimension_name="communication_protocols", contracts=["PEP 544 TraceMemoryProtocol."]
        ),
        boundary_security=ConcernDimension(
            dimension_name="boundary_security", contracts=["PII redaction enabled."]
        ),
        failure_resilience=ConcernDimension(
            dimension_name="failure_resilience", failure_modes=["Retry with backoff."]
        ),
        ambiguity_score=0.10,
    )


def _write_corpus(
    tmp_path: Path,
    inhibitors: str | None = "",
    context: str | None = "",
) -> Path:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    if inhibitors is not None:
        (corpus / "inhibitors.md").write_text(inhibitors, encoding="utf-8")
    if context is not None:
        (corpus / "context-index.md").write_text(context, encoding="utf-8")
    return corpus


def _all_shipped_outputs() -> list[str]:
    mem = FileBackedMemory()
    outputs = list(mem.query_negative_inhibitors("*"))
    outputs += mem.query_negative_inhibitors("sst-custody")
    outputs += mem.query_negative_inhibitors("grill")
    outputs += mem.query_semantic_context(["custody", "mutmut", "trace", "membrane", "bundler"])
    outputs += mem.query_semantic_context(["custody"])
    return outputs


# --- Protocol conformance ---


def test_implements_protocol_exactly() -> None:
    mem = FileBackedMemory()
    assert isinstance(mem, TraceMemoryProtocol)
    assert issubclass(FileBackedMemory, TraceMemoryProtocol)
    for name in ("query_semantic_context", "query_negative_inhibitors"):
        assert inspect.signature(getattr(FileBackedMemory, name)) == inspect.signature(
            getattr(TraceMemoryProtocol, name)
        )


def test_default_corpus_is_live() -> None:
    assert FileBackedMemory().has_live_corpus


# --- No-hallucination ---


def test_known_component_returns_sourced_stamped_excerpts() -> None:
    results = FileBackedMemory().query_negative_inhibitors("sst-custody")
    assert len(results) == 2
    assert results[0].startswith("[source:memory/inhibitors.md#custody-runs-all]")
    assert "EVERY task acceptance command" in results[0]
    assert STAMP_RE.search(results[0]) is not None


def test_unknown_component_returns_empty() -> None:
    mem = FileBackedMemory()
    for unseen in ("quasiflobber", "definitely-not-a-component-xyz", "12345", "trace; DROP TABLE"):
        assert mem.query_negative_inhibitors(unseen) == []


def test_unknown_keywords_return_empty() -> None:
    mem = FileBackedMemory()
    assert mem.query_semantic_context(["quasiflobber"]) == []
    assert mem.query_semantic_context([]) == []
    assert mem.query_semantic_context(["   ", ""]) == []


# --- Match-all parity ---


def test_match_all_spellings_agree() -> None:
    mem = FileBackedMemory()
    star = mem.query_negative_inhibitors("*")
    assert len(star) == 8
    assert mem.query_negative_inhibitors("") == star
    assert mem.query_negative_inhibitors("   ") == star


def test_match_is_case_insensitive_substring() -> None:
    mem = FileBackedMemory()
    upper = mem.query_negative_inhibitors("SST-CUSTODY")
    assert upper == mem.query_negative_inhibitors("sst-custody")
    assert len(mem.query_negative_inhibitors("custody")) >= 2
    assert any("#grill-heuristic" in hit for hit in mem.query_negative_inhibitors("GRILL"))


def test_traceclient_semantics_parity_on_fixture_db(tmp_path: Path) -> None:
    """Same behavior classes as TraceClient on a mirrored fixture DB."""
    client = TraceClient(db_path=tmp_path / "trace.db")
    client.insert_document("d1", "audit.md")
    client.insert_atom("a1", "d1", "SST custody runs acceptance commands for gates")
    client.insert_proposal(
        "p1",
        "REJECTED",
        "negative_inhibitor",
        "SST custody runs acceptance first only",
        component="sst-custody",
    )
    client.insert_proposal(
        "p2",
        "REFUTED",
        "negative_inhibitor",
        "Originals stay authoritative always",
        component="general",
    )
    mem = FileBackedMemory()
    for impl_all in (
        client.query_negative_inhibitors("*"),
        client.query_negative_inhibitors(""),
        mem.query_negative_inhibitors("*"),
        mem.query_negative_inhibitors(""),
    ):
        assert len(impl_all) >= 2
    assert client.query_negative_inhibitors("quasiflobber") == []
    assert mem.query_negative_inhibitors("quasiflobber") == []
    assert client.query_negative_inhibitors("sst-custody") != []
    assert mem.query_negative_inhibitors("sst-custody") != []
    assert client.query_semantic_context([]) == mem.query_semantic_context([]) == []


# --- Citation-first + stamps ---


def test_every_output_citation_first_and_stamped() -> None:
    for output in _all_shipped_outputs():
        assert output.startswith("[source:memory/")
        assert "[source:" in output[:100]
        assert STAMP_RE.search(output) is not None
        assert "\n" not in output


def test_shipped_corpus_has_no_stale_flags() -> None:
    assert all("[STALE]" not in output for output in _all_shipped_outputs())


# --- Semantic search ---


def test_semantic_search_ranks_and_limits() -> None:
    mem = FileBackedMemory()
    hits = mem.query_semantic_context(["custody", "wrapper", "controller"])
    assert hits[0].startswith("[source:memory/context-index.md#d9-custody-seam]")
    assert len(mem.query_semantic_context(["trace", "memory", "mutmut"], max_results=1)) == 1
    assert mem.query_semantic_context(["mutmut"]) != []


# --- Staleness rendering ---


def test_explicit_stale_marker_renders_after_citation(tmp_path: Path) -> None:
    corpus = _write_corpus(
        tmp_path,
        inhibitors=(
            "## Old entry {#old-entry}\n\n- component: general\n- source: somewhere.md\n"
            f"- as-of: stc@{FAKE_SHA}, 2026-01-02\n- stale: yes\n\n> Old but returned.\n"
        ),
    )
    (result,) = FileBackedMemory(corpus_dir=corpus).query_negative_inhibitors("*")
    assert result.startswith("[source:memory/inhibitors.md#old-entry] [STALE] Old but returned.")
    assert STAMP_RE.search(result) is not None


# --- Fixture corpora, absence, malformation ---


def test_missing_corpus_returns_empty_like_missing_db(tmp_path: Path) -> None:
    mem = FileBackedMemory(corpus_dir=tmp_path / "absent")
    assert not mem.has_live_corpus
    assert mem.query_negative_inhibitors("*") == []
    assert mem.query_semantic_context(["anything"]) == []


def test_malformed_corpus_fails_closed(tmp_path: Path) -> None:
    corpus = _write_corpus(
        tmp_path,
        inhibitors="## Bad {#bad}\n\n- component: general\n\n> Missing source and stamp.\n",
    )
    try:
        FileBackedMemory(corpus_dir=corpus)
    except TraceMemoryError:
        return
    raise AssertionError("malformed corpus entry did not raise")


def test_duplicate_anchor_fails_closed(tmp_path: Path) -> None:
    entry = (
        "## Dup {#dup}\n\n- component: general\n- source: s.md\n"
        f"- as-of: stc@{FAKE_SHA}, 2026-09-13\n\n> Body.\n"
    )
    corpus = _write_corpus(tmp_path, inhibitors=entry + "\n" + entry)
    try:
        FileBackedMemory(corpus_dir=corpus)
    except TraceMemoryError:
        return
    raise AssertionError("duplicate anchor did not raise")


# --- Bundler consumer wiring (promotion characterized, not endorsed) ---


def test_bundler_promotes_traces_and_injects_inhibitors() -> None:
    compiler = ContextCompiler(trace_memory=FileBackedMemory())
    spec = _spec_atom(
        "mem-probe",
        "# Custody gate spec\n\nThe mutmut champion gate needs trace context.\n",
    )
    bundle = compiler.compile_task("t1", spec, _toc(), inhibitors=["Do not skip gates."])
    promoted = [inv for inv in bundle.invariants if inv.startswith("[Trace] [source:memory/")]
    assert promoted, "expected [Trace]-promoted citations in bundle invariants"
    assert any(
        inv.startswith("[source:memory/inhibitors.md#") for inv in bundle.negative_inhibitors
    )
    assert compiler.hippocampal_coverage is True
