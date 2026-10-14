"""Wave-2 outcome tests: dedicated OUTCOME_REPORTED kind (REQUEST-2)."""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from sst.cli.main import cli
from sst.core.contracts import TaskPacket
from sst.core.events import EventKind, SSTEvent
from sst.gateway.contracts import ModelCatalog, ModelCatalogEntry, ProviderKind, ProviderProfile
from sst.gateway.gateway import ModelGateway
from sst.sandbox.custody import CandidateCustodyManager
from sst.sandbox.outcomes import (
    LEGACY_OUTCOME_CARRIER_KIND,
    OUTCOME_CARRIER_KIND,
    get_outcomes,
    is_outcome_event,
    report_outcome,
)
from sst.search.controller import SSTSearchController
from sst.search.policy import SearchPolicy
from sst.storage.projection import DAGProjection
from sst.storage.store import SQLiteSSTStore


def _seed_proposed_candidate(store: SQLiteSSTStore, tree_id: str, candidate_id: str) -> None:
    store.append_event(
        SSTEvent(
            event_id="e_tree",
            tree_id=tree_id,
            kind=EventKind.TREE_CREATED,
            idempotency_key=f"init_{tree_id}",
            payload={"tree_id": tree_id, "root_goal": "Goal", "root_node_id": f"root_{tree_id}"},
        )
    )
    store.append_event(
        SSTEvent(
            event_id="e_prop",
            tree_id=tree_id,
            node_id=candidate_id,
            kind=EventKind.NODE_PROPOSED,
            idempotency_key=f"prop_{candidate_id}",
            payload={"title": "Candidate", "target_paths": ["a.py"], "patch_diff": "x = 1\n"},
        )
    )


def _make_controller(tmp_path: Path) -> SSTSearchController:
    src_dir = tmp_path / "repo"
    src_dir.mkdir(exist_ok=True)
    gateway = ModelGateway()
    prof = ProviderProfile(
        name="test-prof",
        kind=ProviderKind.TEST,
        api_base="test://",
        catalog=ModelCatalog(models=[ModelCatalogEntry(id="fake-model", display_label="Fake")]),
    )
    gateway.register_profile(prof)
    task = TaskPacket(
        task_id="t_out",
        goal="Goal",
        source_repo_root=str(src_dir),
        base_commit="c1",
        snapshot_hash="h1",
    )
    return SSTSearchController(
        task=task,
        gateway=gateway,
        store=SQLiteSSTStore(tmp_path / "events.db"),
        custody_manager=CandidateCustodyManager(base_worktree_dir=tmp_path / "worktrees"),
        policy=SearchPolicy(max_iterations=1),
    )


def test_outcome_carrier_is_dedicated_kind(tmp_path: Path) -> None:
    assert OUTCOME_CARRIER_KIND is EventKind.OUTCOME_REPORTED
    assert LEGACY_OUTCOME_CARRIER_KIND is EventKind.WORKER_INVOKED

    store = SQLiteSSTStore(tmp_path / "outcomes.db")
    _seed_proposed_candidate(store, "tree_out", "cand_1")
    report_outcome(store, tree_id="tree_out", candidate_id="cand_1", verdict="OK", actor="op")

    outcomes = get_outcomes(store, "tree_out")
    assert len(outcomes) == 1
    assert outcomes[0].kind is EventKind.OUTCOME_REPORTED


def test_store_report_outcome_delegates_verbatim(tmp_path: Path) -> None:
    store = SQLiteSSTStore(tmp_path / "outcomes.db")
    _seed_proposed_candidate(store, "tree_out", "cand_1")

    seq = store.report_outcome(
        tree_id="tree_out",
        candidate_id="cand_1",
        verdict="ROLLED_BACK_IN_PROD",
        evidence_refs=["deploy-log:42"],
        actor="deploy-pipeline",
        note="Latency regression",
    )

    assert seq > 0
    outcomes = get_outcomes(store, "tree_out")
    assert len(outcomes) == 1
    evt = outcomes[0]
    assert evt.kind is EventKind.OUTCOME_REPORTED
    assert evt.node_id == "cand_1"
    assert evt.actor == "deploy-pipeline"
    assert evt.payload["domain_verdict"] == "ROLLED_BACK_IN_PROD"
    assert evt.payload["evidence_refs"] == ["deploy-log:42"]
    assert evt.payload["note"] == "Latency regression"
    assert evt.payload["sst_authoritative"] is False


def test_controller_report_outcome_delegates_verbatim(tmp_path: Path) -> None:
    controller = _make_controller(tmp_path)
    _seed_proposed_candidate(controller.store, "tree_out", "cand_1")

    seq = controller.report_outcome("tree_out", "cand_1", "USER_ACCEPTED", actor="operator")

    assert seq > 0
    outcomes = get_outcomes(controller.store, "tree_out")
    assert len(outcomes) == 1
    assert outcomes[0].kind is EventKind.OUTCOME_REPORTED
    assert outcomes[0].payload["domain_verdict"] == "USER_ACCEPTED"
    assert outcomes[0].payload["sst_authoritative"] is False


def test_outcome_events_never_mutate_projection(tmp_path: Path) -> None:
    store = SQLiteSSTStore(tmp_path / "outcomes.db")
    _seed_proposed_candidate(store, "tree_out", "cand_1")
    store.append_event(
        SSTEvent(
            event_id="e_score",
            tree_id="tree_out",
            node_id="cand_1",
            kind=EventKind.SCORE_RECORDED,
            idempotency_key="score_cand_1",
            payload={"value_score": 0.9, "verdict": "APPROVE", "critique": "good"},
        )
    )
    before = DAGProjection.replay_events(store.get_events("tree_out"))
    status_before = before.nodes["cand_1"].status

    for verdict in ("ROLLED_BACK_IN_PROD", "APPROVED", "REJECTED", "USER_ACCEPTED"):
        store.report_outcome(
            tree_id="tree_out",
            candidate_id="cand_1",
            verdict=verdict,
            actor="domain",
            idempotency_key=f"outcome_{verdict}",
        )

    after = DAGProjection.replay_events(store.get_events("tree_out"))
    assert after.nodes["cand_1"].status == status_before
    assert after.nodes["cand_1"].cortex_evaluation == before.nodes["cand_1"].cortex_evaluation
    assert len(get_outcomes(store, "tree_out")) == 4


def test_legacy_carrier_still_recognized(tmp_path: Path) -> None:
    store = SQLiteSSTStore(tmp_path / "outcomes.db")
    _seed_proposed_candidate(store, "tree_out", "cand_1")
    store.append_event(
        SSTEvent(
            event_id="e_legacy",
            tree_id="tree_out",
            node_id="cand_1",
            kind=EventKind.WORKER_INVOKED,
            idempotency_key="legacy_outcome",
            payload={"record_type": "domain_outcome", "domain_verdict": "OK", "sst_authoritative": False},
        )
    )
    store.append_event(
        SSTEvent(
            event_id="e_plain",
            tree_id="tree_out",
            node_id="cand_1",
            kind=EventKind.WORKER_INVOKED,
            idempotency_key="plain_worker",
            payload={"task": "unrelated"},
        )
    )

    events = {e.event_id: e for e in store.get_events("tree_out")}
    assert is_outcome_event(events["e_legacy"]) is True
    assert is_outcome_event(events["e_plain"]) is False
    assert [e.event_id for e in get_outcomes(store, "tree_out")] == ["e_legacy"]


def test_outcomes_do_not_satisfy_promotion_gates(tmp_path: Path) -> None:
    """An APPROVED domain verdict alone must not make a candidate promotable."""
    db_dir = tmp_path / ".sst"
    db_dir.mkdir(parents=True, exist_ok=True)
    tree_id = "tree_out_gate"
    store = SQLiteSSTStore(db_dir / f"{tree_id}.db")
    _seed_proposed_candidate(store, tree_id, "cand_1")
    store.report_outcome(
        tree_id=tree_id,
        candidate_id="cand_1",
        verdict="APPROVED",
        actor="domain",
        idempotency_key="outcome_approved",
    )

    runner = CliRunner()
    res = runner.invoke(cli, ["promote", tree_id, "--candidate-id", "cand_1", "--project-path", str(tmp_path)])
    assert res.exit_code != 0
    assert "verifier did not pass" in res.output
