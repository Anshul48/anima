"""Unit tests for the versioned memory-provider seam and CLI provider reporting."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import click
import pytest
from click.testing import CliRunner

from sst.cli.main import cli
from sst.cli.memory import build_memory_provider, format_provider_report
from sst.context.capsule import ContextCapsuleCompiler, memory_tree_payload_fragment
from sst.context.memory_adapter import (
    NullMemoryProvider,
    StaticMemoryProvider,
    TraceLiteDbAdapter,
    wrap_trace_lite_db,
)
from sst.protocols.memory import (
    MEMORY_PROVIDER_PROTOCOL_VERSION,
    MemoryProviderProtocol,
    ProviderStatus,
)


class QuadRef:
    def __init__(self, excerpt: str, path: str, layer: str) -> None:
        self.excerpt = excerpt
        self.path = path
        self.retrieval_layer = layer


class FakeQuadDb:
    def query_quad_channel(self, goal: str, limit_per_channel: int = 5) -> dict[str, list[QuadRef]]:
        _ = (goal, limit_per_channel)
        return {
            "ast_structural": [QuadRef("def foo()", "a.py", "ast_structural")],
            "raptor_summary": [QuadRef("summary text here", "b.py", "raptor_summary")],
            "dense_semantic": [QuadRef("semantic text here", "c.py", "dense_semantic")],
        }


class FakeInhibitorDb:
    def query_negative_inhibitors(self, query: str) -> list[str]:
        _ = query
        return ["Never use unbounded in-memory dict without LRU eviction bounds"]


class FakeEvidenceItem:
    def __init__(self, text: str, source_file: str) -> None:
        self.text = text
        self.source_file = source_file


class FakeEvidenceResult:
    def __init__(self, evidence: list[FakeEvidenceItem]) -> None:
        self.evidence = evidence


class FakeEvidenceDb:
    def query(self, goal: str, top_k: int = 5) -> FakeEvidenceResult:
        _ = (goal, top_k)
        return FakeEvidenceResult([FakeEvidenceItem("prior finding", "notes.md")])


class FakePassage:
    def __init__(self, text: str) -> None:
        self.text = text


class FakePassageResult:
    def __init__(self, passages: list[FakePassage]) -> None:
        self.passages = passages


class FakePassageDb:
    def query(self, goal: str, top_k: int = 5) -> FakePassageResult:
        _ = (goal, top_k)
        return FakePassageResult([FakePassage("passage insight")])


class FailingDb:
    def query_quad_channel(self, goal: str, limit_per_channel: int = 5) -> Any:
        _ = (goal, limit_per_channel)
        raise RuntimeError("quad boom")

    def query_negative_inhibitors(self, query: str) -> Any:
        _ = query
        raise RuntimeError("inhibitor boom")

    def query(self, goal: str, top_k: int = 5) -> Any:
        _ = (goal, top_k)
        raise RuntimeError("query boom")


class PartialDb:
    def query_quad_channel(self, goal: str, limit_per_channel: int = 5) -> Any:
        _ = (goal, limit_per_channel)
        raise RuntimeError("quad boom")

    def query_negative_inhibitors(self, query: str) -> list[str]:
        _ = query
        return ["fallback rule"]


class EmptyDb:
    pass


class RaisingProvider:
    @property
    def provider_name(self) -> str:
        return "raising"

    @property
    def adapter_version(self) -> str:
        return MEMORY_PROVIDER_PROTOCOL_VERSION

    def check_availability(self) -> Any:
        raise RuntimeError("probe boom")

    def query_insights(self, goal: str, limit: int = 5) -> Any:
        _ = (goal, limit)
        raise RuntimeError("query boom")


def test_null_provider_reports_unavailable_with_reason() -> None:
    provider = NullMemoryProvider()
    assert isinstance(provider, MemoryProviderProtocol)
    assert provider.provider_name == "none"
    assert provider.adapter_version == MEMORY_PROVIDER_PROTOCOL_VERSION
    availability = provider.check_availability()
    assert availability.status == ProviderStatus.UNAVAILABLE
    assert availability.last_error == "no memory provider configured"
    assert availability.evidence_refs == []
    result = provider.query_insights("goal")
    assert result.insights == []
    assert result.availability.status == ProviderStatus.UNAVAILABLE


def test_static_provider_is_available_and_bounded() -> None:
    provider = StaticMemoryProvider(["one", "two", "three"])
    assert isinstance(provider, MemoryProviderProtocol)
    result = provider.query_insights("goal", limit=2)
    assert result.availability.status == ProviderStatus.AVAILABLE
    assert [i.text for i in result.insights] == ["one", "two"]
    assert result.availability.evidence_refs == ["static:0", "static:1"]
    assert result.availability.last_error is None


def test_trace_adapter_quad_channel_formats_and_refs() -> None:
    adapter = TraceLiteDbAdapter(FakeQuadDb())
    assert isinstance(adapter, MemoryProviderProtocol)
    assert adapter.check_availability().status == ProviderStatus.AVAILABLE
    result = adapter.query_insights("goal")
    assert result.availability.status == ProviderStatus.AVAILABLE
    assert result.availability.last_error is None
    by_kind = {i.kind: i for i in result.insights}
    assert by_kind["interface"].text == "def foo() in a.py"
    texts = [i.text for i in result.insights if i.kind == "insight"]
    assert "[raptor_summary:b.py] summary text here" in texts
    assert "[dense_semantic:c.py] semantic text here" in texts
    assert "ast_structural:a.py" in result.availability.evidence_refs
    assert "raptor_summary:b.py" in result.availability.evidence_refs


def test_trace_adapter_inhibitor_format_preserved() -> None:
    result = TraceLiteDbAdapter(FakeInhibitorDb()).query_insights("goal")
    assert result.availability.status == ProviderStatus.AVAILABLE
    assert result.insights[0].text.startswith("[NEGATIVE_INHIBITOR] ")
    assert "unbounded in-memory dict" in result.insights[0].text
    assert result.availability.evidence_refs == ["negative-inhibitor:0"]


def test_trace_adapter_generic_evidence_and_passages() -> None:
    ev_result = TraceLiteDbAdapter(FakeEvidenceDb()).query_insights("goal")
    assert ev_result.insights[0].text == "[notes.md] prior finding"
    assert ev_result.availability.evidence_refs == ["notes.md"]

    pass_result = TraceLiteDbAdapter(FakePassageDb()).query_insights("goal")
    assert pass_result.insights[0].text == "passage insight"
    assert pass_result.availability.status == ProviderStatus.AVAILABLE


def test_trace_adapter_surfaces_total_failure() -> None:
    result = TraceLiteDbAdapter(FailingDb()).query_insights("goal")
    assert result.availability.status == ProviderStatus.UNAVAILABLE
    assert result.insights == []
    assert result.availability.last_error is not None
    assert "quad boom" in result.availability.last_error
    assert "inhibitor boom" in result.availability.last_error
    assert "query boom" in result.availability.last_error


def test_trace_adapter_degraded_on_partial_failure() -> None:
    result = TraceLiteDbAdapter(PartialDb()).query_insights("goal")
    assert result.availability.status == ProviderStatus.DEGRADED
    assert "quad boom" in (result.availability.last_error or "")
    assert any("fallback rule" in i.text for i in result.insights)


def test_trace_adapter_rejects_unknown_surface() -> None:
    adapter = TraceLiteDbAdapter(EmptyDb())
    assert adapter.check_availability().status == ProviderStatus.UNAVAILABLE
    result = adapter.query_insights("goal")
    assert result.availability.status == ProviderStatus.UNAVAILABLE
    assert "unsupported trace_lite_db surface" in (result.availability.last_error or "")


def test_wrap_trace_lite_db_dispatch() -> None:
    assert isinstance(wrap_trace_lite_db(None), NullMemoryProvider)
    static = StaticMemoryProvider(["x"])
    assert wrap_trace_lite_db(static) is static
    wrapped = wrap_trace_lite_db(FakeInhibitorDb())
    assert isinstance(wrapped, TraceLiteDbAdapter)


def test_compiler_defaults_to_null_provider(tmp_path: Path) -> None:
    compiler = ContextCapsuleCompiler(workspace_root=tmp_path)
    assert isinstance(compiler.memory_provider, NullMemoryProvider)
    capsule = compiler.compile(goal="Do thing", target_files=[])
    assert capsule.literature_or_prior_insights == []
    assert compiler.last_report is not None
    assert compiler.last_report.provider_name == "none"
    assert compiler.last_report.status == ProviderStatus.UNAVAILABLE
    assert "Memory provider: none" in compiler.describe_memory()


def test_compiler_explicit_provider_wins_over_trace_lite_db(tmp_path: Path) -> None:
    static = StaticMemoryProvider(["explicit insight"])
    compiler = ContextCapsuleCompiler(
        workspace_root=tmp_path,
        trace_lite_db=FakeInhibitorDb(),
        memory_provider=static,
    )
    assert compiler.memory_provider is static
    capsule = compiler.compile(goal="Do thing")
    assert "explicit insight" in capsule.literature_or_prior_insights
    assert compiler.last_report is not None
    assert compiler.last_report.provider_name == "static"


def test_compiler_wraps_duck_typed_trace_lite_db(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "cache.py").write_text("class Cache: pass\n", encoding="utf-8")
    compiler = ContextCapsuleCompiler(workspace_root=workspace, trace_lite_db=FakeInhibitorDb())
    assert isinstance(compiler.memory_provider, TraceLiteDbAdapter)
    capsule = compiler.compile(goal="Design high performance cache", target_files=["cache.py"])
    assert any("[NEGATIVE_INHIBITOR]" in s for s in capsule.literature_or_prior_insights)
    assert any("unbounded in-memory dict" in s for s in capsule.literature_or_prior_insights)
    assert any(s.startswith("[memory-provider:trace-lite-db") for s in capsule.literature_or_prior_insights)
    assert compiler.last_report is not None
    assert compiler.last_report.status == ProviderStatus.AVAILABLE
    assert compiler.last_report.evidence_refs == ["negative-inhibitor:0"]
    fragment = memory_tree_payload_fragment(compiler.last_report)
    assert fragment["memory_provider"] == "trace-lite-db"
    assert fragment["memory_availability"] == "AVAILABLE"
    assert fragment["memory_adapter_version"] == MEMORY_PROVIDER_PROTOCOL_VERSION
    assert fragment["memory_last_error"] is None


def test_compiler_quad_interfaces_merge_with_ast(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "mod.py").write_text("def local(): pass\n", encoding="utf-8")
    compiler = ContextCapsuleCompiler(workspace_root=workspace, trace_lite_db=FakeQuadDb())
    capsule = compiler.compile(goal="goal", target_files=["mod.py"])
    assert "def foo() in a.py" in capsule.interfaces
    assert any("def local" in iface for iface in capsule.interfaces)
    assert any("[raptor_summary:b.py]" in s for s in capsule.literature_or_prior_insights)


def test_compiler_survives_raising_provider_and_reports(tmp_path: Path) -> None:
    compiler = ContextCapsuleCompiler(workspace_root=tmp_path, memory_provider=RaisingProvider())
    capsule = compiler.compile(goal="goal")
    assert capsule.goal == "goal"
    assert compiler.last_report is not None
    assert compiler.last_report.status == ProviderStatus.UNAVAILABLE
    assert compiler.last_report.last_error is not None
    assert "query boom" in compiler.last_report.last_error
    assert "last_error=" in compiler.describe_memory()


def test_memory_tree_payload_fragment_empty_when_no_report() -> None:
    assert memory_tree_payload_fragment(None) == {}


def test_build_memory_provider_specs() -> None:
    assert build_memory_provider(None) is None
    assert build_memory_provider("none") is None
    static = build_memory_provider("static", insights=["a", "b"])
    assert isinstance(static, StaticMemoryProvider)
    assert static.check_availability().status == ProviderStatus.AVAILABLE
    with pytest.raises(click.ClickException, match="Unknown memory provider spec"):
        build_memory_provider("trace-lite")


def test_format_provider_report_branches() -> None:
    none_report = format_provider_report(None)
    assert "Memory provider: none" in none_report
    assert "UNAVAILABLE" in none_report
    static_report = format_provider_report(StaticMemoryProvider(["x"]))
    assert "Memory provider: static" in static_report
    assert "AVAILABLE" in static_report


def test_cli_run_help_exposes_memory_options() -> None:
    runner = CliRunner()
    res = runner.invoke(cli, ["run", "--help"])
    assert res.exit_code == 0
    assert "--memory-provider" in res.output
    assert "--memory-insight" in res.output


def test_cli_run_rejects_unknown_memory_provider(tmp_path: Path) -> None:
    runner = CliRunner()
    res = runner.invoke(
        cli,
        ["run", "--goal", "x", "--project-path", str(tmp_path), "--memory-provider", "bogus"],
    )
    assert res.exit_code != 0
    assert "Unknown memory provider spec" in res.output
