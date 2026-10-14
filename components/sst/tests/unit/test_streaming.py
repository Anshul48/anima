"""Unit tests for Cytoscape Read Model Snapshot, Event Deltas, and XSS Hardening."""

from sst.core.events import EventKind, SSTEvent
from sst.core.models import (
    CortexEvaluation,
    DomainMode,
    NodeRole,
    NodeStatus,
    PayloadType,
    SSTNode,
    SSTTree,
)
from sst.visualizer import render_html_visualizer, to_cytoscape_elements, to_event_delta_payload


def test_to_cytoscape_elements() -> None:
    root = SSTNode(
        node_id="root_1",
        tree_id="t1",
        depth=0,
        domain=DomainMode.AUTOBUILD,
        role=NodeRole.CORTEX_PLANNER,
        title="Root goal",
        payload_type=PayloadType.GOAL,
        content="Root goal content",
        status=NodeStatus.APPROVED_CORTEX,
    )
    child = SSTNode(
        node_id="child_1",
        parent_id="root_1",
        tree_id="t1",
        depth=1,
        domain=DomainMode.AUTOBUILD,
        role=NodeRole.ADHD_EXPLORER,
        title="Divergent child",
        payload_type=PayloadType.CODE_DIFF,
        content="child diff",
        status=NodeStatus.APPROVED_CORTEX,
        cortex_evaluation=CortexEvaluation(verdict="APPROVE", value_score=0.92, critique="Good design"),
    )

    tree = SSTTree(
        tree_id="t1",
        domain=DomainMode.AUTOBUILD,
        root_goal="Test",
        root_node_id="root_1",
        nodes={"root_1": root, "child_1": child},
        winning_path=["root_1", "child_1"],
    )

    elements = to_cytoscape_elements(tree)
    assert len(elements) == 3

    node_elements = [el for el in elements if el["group"] == "nodes"]
    edge_elements = [el for el in elements if el["group"] == "edges"]

    assert len(node_elements) == 2
    assert len(edge_elements) == 1

    child_el = [n for n in node_elements if n["data"]["id"] == "child_1"][0]
    assert child_el["data"]["valueScore"] == 0.92
    assert child_el["data"]["isWinning"] is True

    edge = edge_elements[0]
    assert edge["data"]["source"] == "root_1"
    assert edge["data"]["target"] == "child_1"
    assert edge["data"]["isWinning"] is True


def test_to_cytoscape_elements_colimit_synthesis_multi_parent() -> None:
    """Verifies that colimit synthesis nodes generate edges from all parent branches."""
    root = SSTNode(
        node_id="root",
        tree_id="t1",
        depth=0,
        domain=DomainMode.AUTOBUILD,
        role=NodeRole.PLANNER,
        title="Root",
        payload_type=PayloadType.GOAL,
        content="Goal",
        status=NodeStatus.APPROVED_CORTEX,
    )
    branch_a = SSTNode(
        node_id="b_a",
        parent_id="root",
        tree_id="t1",
        depth=1,
        domain=DomainMode.AUTOBUILD,
        role=NodeRole.DIVERGE,
        title="Branch A",
        payload_type=PayloadType.CODE_DIFF,
        content="code a",
        status=NodeStatus.PASS_DETERMINISTIC,
    )
    branch_b = SSTNode(
        node_id="b_b",
        parent_id="root",
        tree_id="t1",
        depth=1,
        domain=DomainMode.AUTOBUILD,
        role=NodeRole.REFINE,
        title="Branch B",
        payload_type=PayloadType.CODE_DIFF,
        content="code b",
        status=NodeStatus.PASS_DETERMINISTIC,
    )
    synth = SSTNode(
        node_id="synth",
        parent_id="b_a",
        tree_id="t1",
        depth=2,
        domain=DomainMode.AUTOBUILD,
        role=NodeRole.SYNTHESIZE,
        title="Synthesized",
        payload_type=PayloadType.SYNTHESIS,
        content="synth code",
        status=NodeStatus.SYNTHESIZED,
        metadata={"parent_ids": ["b_a", "b_b"]},
    )
    tree = SSTTree(
        tree_id="t1",
        domain=DomainMode.AUTOBUILD,
        root_goal="Goal",
        root_node_id="root",
        nodes={"root": root, "b_a": branch_a, "b_b": branch_b, "synth": synth},
        winning_path=["root", "b_a", "synth"],
    )

    elements = to_cytoscape_elements(tree)
    edge_elements = [el for el in elements if el["group"] == "edges"]
    # Should have 4 edges: root->b_a, root->b_b, b_a->synth, b_b->synth
    assert len(edge_elements) == 4
    targets_for_synth = [e["data"]["source"] for e in edge_elements if e["data"]["target"] == "synth"]
    assert "b_a" in targets_for_synth
    assert "b_b" in targets_for_synth


def test_to_event_delta_payload() -> None:
    events = [
        SSTEvent(
            event_id="evt_01",
            tree_id="t_stream",
            kind=EventKind.TREE_CREATED,
            idempotency_key="k1",
            payload={"goal": "Stream test"},
        ),
        SSTEvent(
            event_id="evt_02",
            tree_id="t_stream",
            node_id="node_a",
            kind=EventKind.NODE_PROPOSED,
            idempotency_key="k2",
            payload={"title": "Proposed node"},
        ),
    ]

    deltas = to_event_delta_payload(events)
    assert len(deltas) == 2
    assert deltas[0]["kind"] == "TREE_CREATED"
    assert deltas[1]["node_id"] == "node_a"


def test_render_html_visualizer_xss_protection() -> None:
    malicious_data = {
        "rootGoal": "</script><script>alert('xss')</script>",
        "nodes": [
            {
                "id": "node_xss",
                "title": "<img src=x onerror=alert('xss')>",
                "role": "ADHD_EXPLORER",
                "status": "APPROVED_CORTEX",
                "diffPreview": "<script>fetch('http://evil.com')</script>",
            }
        ],
        "edges": [],
    }

    html = render_html_visualizer(malicious_data)
    assert isinstance(html, str)
    # The script tag closing sequence </script> inside JSON should be safely escaped as <\/script>
    assert "<\\/script><script>alert('xss')<\\/script>" in html
    # In JS click handler, escapeHtml should be present
    assert "escapeHtml" in html
