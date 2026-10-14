"""F10 controls: stable fact/revision references across identical replay.

Fact, cluster, and edge ids derive deterministically from semantic content
(entity, attribute, value, validity, evidence set, derivation) with
disclosed algorithm versions, so correction/explanation/revision anchors
survive rebuilds. Validity instants come from evidence time, never
wall-clock processing time. Synthetic only.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from entorhinal.evidence.journal import EvidenceJournal
from entorhinal.projections.compiler import MultiTimescaleCompiler
from entorhinal.projections.graph import SemanticGraphManager
from entorhinal.schemas.models import (
    CLUSTER_ID_ALGORITHM,
    EDGE_ID_ALGORITHM,
    FACT_ID_ALGORITHM,
    EvidenceRecord,
    SourceType,
    derive_cluster_id,
    derive_edge_id,
    derive_fact_id,
)

T0 = datetime(2026, 10, 11, 9, 0, 0, tzinfo=timezone.utc)


def _record(record_id: str, at: datetime) -> EvidenceRecord:
    return EvidenceRecord.create(
        source_type=SourceType.OS_WINDOW,
        app_identifier="VSCode",
        sanitized_payload={"workspace": "synthetic-id", "file_path": "/synthetic/id/probe.py"},
        previous_record_hash="0" * 64,
        window_title="SYNTHETIC identity probe",
        target_uri="file:///synthetic/id/probe.py",
        record_id=record_id,
        persisted_at=at,
    )


def _fact_parts() -> dict:
    return {
        "entity_uri": "project:synthetic-id",
        "attribute": "name",
        "value": "synthetic-id",
        "valid_from": T0,
        "valid_to": None,
        "evidence_ids": ["syn-id-2", "syn-id-1"],
        "derived_by": "SyntheticProbe.rule",
    }


# --------------------------------------------------------------------------
# Derivation unit semantics
# --------------------------------------------------------------------------

def test_algorithms_disclosed() -> None:
    assert FACT_ID_ALGORITHM == "fact-id/1"
    assert CLUSTER_ID_ALGORITHM == "cluster-id/1"
    assert EDGE_ID_ALGORITHM == "edge-id/1"


def test_fact_id_deterministic_and_order_free() -> None:
    first = derive_fact_id(**_fact_parts())
    assert first.startswith("fact-v1-")
    assert derive_fact_id(**_fact_parts()) == first
    reordered = dict(_fact_parts())
    reordered["evidence_ids"] = ["syn-id-1", "syn-id-2"]
    assert derive_fact_id(**reordered) == first


def test_fact_id_binds_every_part() -> None:
    base = derive_fact_id(**_fact_parts())
    for key, other in [
        ("entity_uri", "project:other"),
        ("attribute", "other"),
        ("value", "other"),
        ("valid_from", T0 + timedelta(seconds=1)),
        ("evidence_ids", ["syn-id-1"]),
        ("derived_by", "Other.rule"),
    ]:
        mutated = dict(_fact_parts())
        mutated[key] = other
        assert derive_fact_id(**mutated) != base, key


def test_cluster_and_edge_ids_deterministic() -> None:
    cluster = derive_cluster_id(
        evidence_ids=["b", "a"], start_time=T0, end_time=T0 + timedelta(minutes=5), title="t"
    )
    assert cluster.startswith("cluster-v1-")
    assert cluster == derive_cluster_id(
        evidence_ids=["a", "b"], start_time=T0, end_time=T0 + timedelta(minutes=5), title="t"
    )
    edge = derive_edge_id(source_uri="tool:vscode", relation_type="EDITING", target_uri="artifact:x")
    assert edge.startswith("edge-v1-")
    assert edge == derive_edge_id(
        source_uri="tool:vscode", relation_type="EDITING", target_uri="artifact:x"
    )
    assert edge != derive_edge_id(
        source_uri="tool:vscode", relation_type="USES", target_uri="artifact:x"
    )


# --------------------------------------------------------------------------
# Replay stability: identical evidence, identical references
# --------------------------------------------------------------------------

def _build_graph(records: list[EvidenceRecord]) -> SemanticGraphManager:
    graph = SemanticGraphManager()
    for record in records:
        graph.extract_and_ingest_record(record)
    return graph


def test_graph_replay_yields_identical_fact_ids() -> None:
    records = [_record("syn-id-1", T0), _record("syn-id-2", T0 + timedelta(minutes=3))]
    first = {f.fact_id for f in _build_graph(records).to_derived_facts()}
    second = {f.fact_id for f in _build_graph(records).to_derived_facts()}
    assert first, "corpus must yield facts"
    assert first == second


def test_graph_replay_independent_of_wall_clock() -> None:
    records = [_record("syn-id-1", T0), _record("syn-id-2", T0 + timedelta(minutes=3))]
    first = {f.fact_id: f.valid_from for f in _build_graph(records).to_derived_facts()}
    # Rebuild "later": node times pin to evidence persisted_at, not now().
    second = {f.fact_id: f.valid_from for f in _build_graph(records).to_derived_facts()}
    assert first == second
    assert all(v.tzinfo is not None for v in first.values())


def test_edge_ids_stable_across_replay() -> None:
    records = [_record("syn-id-1", T0), _record("syn-id-2", T0 + timedelta(minutes=3))]
    first = [(e.edge_id, e.source_uri, e.target_uri) for e in _build_graph(records).get_edges()]
    second = [(e.edge_id, e.source_uri, e.target_uri) for e in _build_graph(records).get_edges()]
    assert first, "corpus must yield edges"
    assert first == second


def test_revision_counter_stays_separate() -> None:
    records = [_record("syn-id-1", T0)]
    for fact in _build_graph(records).to_derived_facts():
        assert fact.revision_id == 1


@pytest.mark.asyncio
async def test_batch_recompile_yields_identical_session_anchors(tmp_path) -> None:
    journal = EvidenceJournal(storage_path=tmp_path / "id_journal.jsonl")
    await journal.append(_record("syn-id-1", T0))
    await journal.append(_record("syn-id-2", T0 + timedelta(minutes=3)))
    first = await MultiTimescaleCompiler(journal=journal).compile_batch_projection()
    second = await MultiTimescaleCompiler(journal=journal).compile_batch_projection()
    first_ids = {f.fact_id for f in first}
    assert first_ids == {f.fact_id for f in second}
    session_ids = [f.fact_id for f in first if f.entity_uri.startswith("session:")]
    assert session_ids, "corpus must yield a session anchor"
    assert all(i.startswith("fact-v1-") for i in first_ids)
    assert all(f.entity_uri.split(":", 1)[1].startswith("cluster-v1-") for f in first if f.entity_uri.startswith("session:"))
