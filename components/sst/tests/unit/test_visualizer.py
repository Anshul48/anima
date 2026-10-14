"""Tests for SST visualizer HTML generation and live server."""

import json
import socket
import urllib.request
from typing import Any

from sst.core.events import EventKind, SSTEvent
from sst.core.models import (
    DomainMode,
    NodeRole,
    NodeStatus,
    PayloadType,
    SSTNode,
    SSTTree,
)
from sst.storage.serializer import serialize_sst_tree
from sst.visualizer import render_html_visualizer, start_visualizer_server


def test_sst_visualizer_html_rendering() -> None:
    tree = SSTTree(
        tree_id="tree_vis_01",
        domain=DomainMode.AUTOBUILD,
        root_goal="Build High Throughput Stream Parser",
        root_node_id="root_01",
    )
    root = SSTNode(
        node_id="root_01",
        tree_id="tree_vis_01",
        domain=DomainMode.AUTOBUILD,
        role=NodeRole.CORTEX_PLANNER,
        title="Root Parser Goal",
        payload_type=PayloadType.GOAL,
        content="Parser Goal Content",
        status=NodeStatus.APPROVED_CORTEX,
    )
    child = SSTNode(
        node_id="child_01",
        parent_id="root_01",
        tree_id="tree_vis_01",
        domain=DomainMode.AUTOBUILD,
        role=NodeRole.ASD_EXPLOITER,
        title="Zero-Copy SIMD Parser",
        payload_type=PayloadType.CODE_DIFF,
        content="class SIMDParser: pass",
        status=NodeStatus.APPROVED_CORTEX,
    )
    tree.add_node(root)
    tree.add_node(child)
    tree.winning_path = ["root_01", "child_01"]

    graph_data = serialize_sst_tree(tree)
    html = render_html_visualizer(graph_data)

    assert "<!DOCTYPE html>" in html
    assert "AuDHD State Space Tree Visualizer" in html
    assert "tree_vis_01" in html
    assert "Zero-Copy SIMD Parser" in html
    assert "cytoscape" in html


def test_live_visualizer_endpoints_and_sse() -> None:
    tree = SSTTree(
        tree_id="tree_server_test",
        domain=DomainMode.AUTOBUILD,
        root_goal="Test Server Endpoints",
        root_node_id="root_srv",
    )
    root = SSTNode(
        node_id="root_srv",
        tree_id="tree_server_test",
        domain=DomainMode.AUTOBUILD,
        role=NodeRole.CORTEX_PLANNER,
        title="Root Server Node",
        payload_type=PayloadType.GOAL,
        content="Goal Content",
        status=NodeStatus.APPROVED_CORTEX,
    )
    tree.add_node(root)
    tree_data = serialize_sst_tree(tree)

    events = [
        SSTEvent(
            event_id="evt_srv_01",
            tree_id="tree_server_test",
            kind=EventKind.TREE_CREATED,
            idempotency_key="k_srv_1",
            payload={"goal": "Test Server Endpoints"},
        )
    ]

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        port = int(s.getsockname()[1])

    server = start_visualizer_server(tree_data=tree_data, port=port, events_data=events)
    try:
        # 1. Test GET / -> HTML UI
        req = urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=3)
        assert req.status == 200
        assert "text/html" in req.headers.get("Content-Type", "")
        html_body = req.read().decode("utf-8")
        assert "AuDHD State Space Tree Visualizer" in html_body
        assert "tree_server_test" in html_body

        # 2. Test GET /api/tree -> JSON Tree
        req_tree = urllib.request.urlopen(f"http://127.0.0.1:{port}/api/tree", timeout=3)
        assert req_tree.status == 200
        assert "application/json" in req_tree.headers.get("Content-Type", "")
        tree_json: dict[str, Any] = json.loads(req_tree.read().decode("utf-8"))
        assert tree_json["treeId"] == "tree_server_test"
        assert len(tree_json["nodes"]) == 1

        # 3. Test GET /api/events -> JSON Events
        req_events = urllib.request.urlopen(f"http://127.0.0.1:{port}/api/events", timeout=3)
        assert req_events.status == 200
        assert "application/json" in req_events.headers.get("Content-Type", "")
        events_json = json.loads(req_events.read().decode("utf-8"))
        assert len(events_json) == 1
        assert events_json[0]["kind"] == "TREE_CREATED"

        # 4. Test GET /api/stream -> SSE Stream
        req_stream = urllib.request.urlopen(f"http://127.0.0.1:{port}/api/stream", timeout=3)
        assert req_stream.status == 200
        assert "text/event-stream" in req_stream.headers.get("Content-Type", "")
        # Read the first line of the SSE stream (data: ...)
        first_line = req_stream.readline().decode("utf-8")
        assert first_line.startswith("data: ")
        payload_str = first_line[len("data: ") :].strip()
        sse_data = json.loads(payload_str)
        assert sse_data["type"] == "snapshot"
        assert sse_data["tree"]["treeId"] == "tree_server_test"
        req_stream.close()

    finally:
        server.shutdown()
        server.server_close()


def test_sst_visualizer_temporal_elements() -> None:
    from sst.visualizer import to_cytoscape_elements

    tree = SSTTree(
        tree_id="tree_temporal_01",
        domain=DomainMode.AUTORESEARCH,
        root_goal="Investigate Stigmergic Memory Systems",
        root_node_id="root_t0",
    )
    root = SSTNode(
        node_id="root_t0",
        tree_id="tree_temporal_01",
        domain=DomainMode.AUTORESEARCH,
        role=NodeRole.PLANNER,
        title="Stigmergy Invariants",
        payload_type=PayloadType.GOAL,
        content="# Stigmergic Memory\n- Trace-based coordination",
        status=NodeStatus.APPROVED_CORTEX,
        metadata={"epoch": 0, "notes": "# Stigmergic Memory\n- Trace-based coordination"},
    )
    child_v1 = SSTNode(
        node_id="concept_v1",
        parent_id="root_t0",
        tree_id="tree_temporal_01",
        depth=1,
        domain=DomainMode.AUTORESEARCH,
        role=NodeRole.DIVERGE,
        title="Physical Memory Ledger",
        payload_type=PayloadType.HYPOTHESIS,
        content="Ledger on disk without index",
        status=NodeStatus.PASS_DETERMINISTIC,
        metadata={
            "epoch": 1,
            "valid_to": "2026-09-10T00:00:00Z",
            "superseded_by": "concept_v2",
            "notes": "Direct file appending",
        },
    )
    child_v2 = SSTNode(
        node_id="concept_v2",
        parent_id="root_t0",
        tree_id="tree_temporal_01",
        depth=2,
        domain=DomainMode.AUTORESEARCH,
        role=NodeRole.SYNTHESIZE,
        title="LanceDB Content-Addressed Ledger",
        payload_type=PayloadType.SYNTHESIS,
        content="Immutable atoms with columnar vector indexing",
        status=NodeStatus.SYNTHESIZED,
        metadata={
            "epoch": 2,
            "branched_from": "concept_v1",
            "notes": "LanceDB hybrid index",
            "parent_ids": ["concept_v1"],
        },
    )
    tree.add_node(root)
    tree.add_node(child_v1)
    tree.add_node(child_v2)

    elements = to_cytoscape_elements(tree)
    nodes = [e for e in elements if e.get("group") == "nodes"]
    edges = [e for e in elements if e.get("group") == "edges"]

    assert len(nodes) == 3
    assert len(edges) >= 2

    # Check temporal attributes on nodes
    v1_el = next(n for n in nodes if n["data"]["id"] == "concept_v1")
    assert v1_el["data"]["epoch"] == 1
    assert v1_el["data"]["validTo"] == "2026-09-10T00:00:00Z"
    assert v1_el["data"]["supersededBy"] == "concept_v2"
    assert "createdAt" in v1_el["data"]
    assert "updatedAt" in v1_el["data"]

    v2_el = next(n for n in nodes if n["data"]["id"] == "concept_v2")
    assert v2_el["data"]["epoch"] == 2
    assert v2_el["data"]["branchedFrom"] == "concept_v1"


def test_sst_visualizer_timeline_scrubber_html() -> None:
    tree_data = {
        "treeId": "tree_scrubber_test",
        "rootGoal": "Scrubber Test Goal",
        "nodes": [
            {
                "id": "node_0",
                "title": "Genesis Concept",
                "role": "PLANNER",
                "status": "APPROVED_CORTEX",
                "epoch": 0,
                "createdAt": "2026-09-01T10:00:00Z",
                "notes": "### Genesis Idea\nInitial concept formulation.",
            },
            {
                "id": "node_1",
                "title": "Superseded Branch",
                "role": "DIVERGE",
                "status": "SUPERSEDED",
                "epoch": 1,
                "createdAt": "2026-09-02T12:00:00Z",
                "validTo": "2026-09-05T00:00:00Z",
                "supersededBy": "node_2",
                "notes": "Early prototype, superseded by node_2.",
            },
            {
                "id": "node_2",
                "title": "Refined Branch",
                "role": "REFINE",
                "status": "ACTIVE",
                "epoch": 2,
                "createdAt": "2026-09-05T00:00:00Z",
                "branchedFrom": "node_1",
                "notes": "Refined architecture note.",
            },
        ],
        "edges": [
            {"id": "e01", "source": "node_0", "target": "node_1", "status": "SUPERSEDED"},
            {"id": "e02", "source": "node_0", "target": "node_2", "status": "ACTIVE"},
        ],
    }

    html = render_html_visualizer(tree_data)

    # Scrubber and timeline UI controls
    assert 'id="timeline-bar"' in html
    assert 'id="timeline-slider"' in html
    assert 'id="btn-play"' in html
    assert 'id="btn-all-time"' in html
    assert 'id="timeline-label"' in html
    assert 'id="layout-select"' in html

    # Layout options
    assert "Layout: Hierarchical (TB)" in html
    assert "Layout: Chronological (LR)" in html
    assert "Layout: Concentric (Epochs)" in html

    # Markdown and inspector
    assert "renderMarkdown" in html
    assert "selectNodeById" in html
    assert "Lineage &amp; Temporal Coordinates" in html or "Lineage & Temporal Coordinates" in html
