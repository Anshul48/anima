"""Wave-2 recovery tests: get_search_result reconstruction round-trips."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from sst.core.contracts import SearchResult, TaskPacket
from sst.core.errors import IncompleteSearchError
from sst.core.events import EventKind, SSTEvent
from sst.gateway.contracts import (
    GatewayRequest,
    GatewayResponse,
    ModelCatalog,
    ModelCatalogEntry,
    ProviderKind,
    ProviderProfile,
    UnreachableEndpointError,
)
from sst.gateway.gateway import ModelGateway
from sst.sandbox.custody import CandidateCustodyManager
from sst.search.controller import SSTSearchController
from sst.search.policy import SearchPolicy
from sst.search.recovery import get_search_result
from sst.storage.store import SQLiteSSTStore

GOOD_CODE = "def mul(a, b): return a * b\n"
BAD_CODE = "def mul(a, b): return a + b\n"


class RoleFailingGateway(ModelGateway):
    """Deterministic gateway that fails selected roles with a categorized error."""

    def __init__(self, fail_roles: set[str] | None = None, diverge_code: str = GOOD_CODE) -> None:
        super().__init__()
        prof = ProviderProfile(
            name="test-prof",
            kind=ProviderKind.TEST,
            api_base="test://",
            catalog=ModelCatalog(models=[ModelCatalogEntry(id="fake-model", display_label="Fake")]),
        )
        self.register_profile(prof)
        for role in ("diverge", "refine", "critique", "synthesize"):
            self.set_route(role, "test-prof", "fake-model")
        self.fail_roles = set(fail_roles or ())
        self.diverge_code = diverge_code

    def invoke(self, request: GatewayRequest) -> GatewayResponse:
        if request.role in self.fail_roles:
            raise UnreachableEndpointError("Cannot connect to test provider", profile="test-prof")
        if request.role == "critique":
            content = '{"value_score": 0.95, "verdict": "APPROVE", "rationale": "High quality solution"}'
        else:
            content = self.diverge_code
        return GatewayResponse(
            content=content,
            profile="test-prof",
            model="fake-model",
            prompt_tokens=50,
            completion_tokens=50,
            total_tokens=100,
        )


def _make_controller(tmp_path: Path, gateway: ModelGateway, policy: SearchPolicy, tag: str) -> SSTSearchController:
    src_dir = tmp_path / "repo"
    src_dir.mkdir(exist_ok=True)
    (src_dir / "math_mod.py").write_text("def mul(a, b): return a + b\n", encoding="utf-8")
    (src_dir / "test_math.py").write_text("from math_mod import mul\nassert mul(3, 4) == 12\n", encoding="utf-8")
    task = TaskPacket(
        task_id=f"t_{tag}",
        goal="Implement correct multiplication",
        source_repo_root=str(src_dir),
        base_commit="c1",
        snapshot_hash="h1",
        allowed_paths=["math_mod.py"],
        acceptance_commands=["python test_math.py"],
    )
    return SSTSearchController(
        task=task,
        gateway=gateway,
        store=SQLiteSSTStore(tmp_path / f"events_{tag}.db"),
        custody_manager=CandidateCustodyManager(base_worktree_dir=tmp_path / "worktrees"),
        policy=policy,
    )


def _assert_round_trip(live: SearchResult, recovered: SearchResult) -> None:
    """Field-level equality between a live envelope and its log reconstruction."""
    assert recovered.tree_id == live.tree_id
    assert recovered.termination_reason == live.termination_reason
    assert (recovered.champion is None) == (live.champion is None)
    if live.champion is not None:
        assert recovered.champion is not None
        for field in ("candidate_id", "title", "rationale", "patch_diff", "target_paths", "role", "model_id"):
            assert getattr(recovered.champion, field) == getattr(live.champion, field), f"champion.{field} differs"
    assert [a.candidate.candidate_id for a in recovered.alternatives] == [
        a.candidate.candidate_id for a in live.alternatives
    ]
    for rec_alt, live_alt in zip(recovered.alternatives, live.alternatives, strict=True):
        assert rec_alt.candidate.patch_diff == live_alt.candidate.patch_diff
        assert (rec_alt.score is None) == (live_alt.score is None)
        if live_alt.score is not None:
            assert rec_alt.score is not None
            assert rec_alt.score.normalized_reward == live_alt.score.normalized_reward
            assert rec_alt.score.critic_verdict == live_alt.score.critic_verdict
            assert rec_alt.score.critic_rationale == live_alt.score.critic_rationale
        assert (rec_alt.verifier_outcome is None) == (live_alt.verifier_outcome is None)
        if live_alt.verifier_outcome is not None:
            assert rec_alt.verifier_outcome is not None
            assert rec_alt.verifier_outcome.passed == live_alt.verifier_outcome.passed
            assert rec_alt.verifier_outcome.exit_code == live_alt.verifier_outcome.exit_code
        assert rec_alt.evidence_refs == live_alt.evidence_refs
        assert rec_alt.evidence_refs, "alternatives must carry evidence refs"
    assert recovered.budget_consumed == live.budget_consumed
    assert recovered.provider_errors == live.provider_errors
    assert recovered.event_log_ref == live.event_log_ref


def test_round_trip_champion_run(tmp_path: Path) -> None:
    controller = _make_controller(
        tmp_path,
        RoleFailingGateway(),
        SearchPolicy(max_iterations=2, branching_factor=1, max_depth=2),
        "rec_champ",
    )
    live = asyncio.run(controller.run_search("tree_rec_champ"))
    assert live.champion is not None

    recovered = get_search_result(controller.store, "tree_rec_champ")
    _assert_round_trip(live, recovered)


def test_round_trip_no_candidate_failed_verifier(tmp_path: Path) -> None:
    controller = _make_controller(
        tmp_path,
        RoleFailingGateway(diverge_code=BAD_CODE),
        SearchPolicy(max_iterations=1, branching_factor=1, max_depth=2),
        "rec_fail",
    )
    live = asyncio.run(controller.run_search("tree_rec_fail"))
    assert live.champion is None
    assert len(live.alternatives) == 1

    recovered = get_search_result(controller.store, "tree_rec_fail")
    _assert_round_trip(live, recovered)


def test_round_trip_provider_errors_preserved(tmp_path: Path) -> None:
    controller = _make_controller(
        tmp_path,
        RoleFailingGateway(fail_roles={"critique"}),
        SearchPolicy(max_iterations=1, branching_factor=1, max_depth=2),
        "rec_perr",
    )
    live = asyncio.run(controller.run_search("tree_rec_perr"))
    assert len(live.provider_errors) == 1

    recovered = get_search_result(controller.store, "tree_rec_perr")
    _assert_round_trip(live, recovered)
    assert recovered.provider_errors[0].category == "unreachable_endpoint"


def test_round_trip_budget_exhaustion(tmp_path: Path) -> None:
    controller = _make_controller(
        tmp_path,
        RoleFailingGateway(),
        SearchPolicy(max_iterations=5, branching_factor=1, max_token_budget=50),
        "rec_budget",
    )
    live = asyncio.run(controller.run_search("tree_rec_budget"))

    recovered = get_search_result(controller.store, "tree_rec_budget")
    _assert_round_trip(live, recovered)


def test_round_trip_multi_branch_ranking(tmp_path: Path) -> None:
    """Two evaluated candidates must reconstruct in the same ranked order."""

    class TwoBranchGateway(RoleFailingGateway):
        def invoke(self, request: GatewayRequest) -> GatewayResponse:
            if request.role == "diverge":
                content = json.dumps(
                    {
                        "branches": [
                            {
                                "branch_index": i,
                                "strategy_title": f"Branch {i}",
                                "hypothesis_or_rationale": "Explore",
                                "proposed_changes": GOOD_CODE,
                            }
                            for i in range(2)
                        ]
                    }
                )
                return GatewayResponse(
                    content=content,
                    profile="test-prof",
                    model="fake-model",
                    prompt_tokens=50,
                    completion_tokens=50,
                    total_tokens=100,
                )
            return super().invoke(request)

    controller = _make_controller(
        tmp_path,
        TwoBranchGateway(),
        SearchPolicy(max_iterations=1, branching_factor=2, max_depth=2),
        "rec_rank",
    )
    live = asyncio.run(controller.run_search("tree_rec_rank"))
    assert len(live.alternatives) >= 2

    recovered = get_search_result(controller.store, "tree_rec_rank")
    _assert_round_trip(live, recovered)


def test_missing_finished_marker_raises(tmp_path: Path) -> None:
    store = SQLiteSSTStore(tmp_path / "events.db")
    store.append_event(
        SSTEvent(
            event_id="e_tree",
            tree_id="tree_crashed",
            kind=EventKind.TREE_CREATED,
            idempotency_key="init_tree_crashed",
            payload={"tree_id": "tree_crashed", "root_goal": "Goal", "root_node_id": "root_tree_crashed"},
        )
    )

    try:
        get_search_result(store, "tree_crashed")
    except IncompleteSearchError as exc:
        assert "SEARCH_COMPLETED" in exc.message
    else:
        raise AssertionError("expected IncompleteSearchError for a run without a finished-marker")

    try:
        get_search_result(store, "tree_unknown")
    except IncompleteSearchError as exc:
        assert "tree_unknown" in exc.message
    else:
        raise AssertionError("expected IncompleteSearchError for an unknown tree")


def test_dangling_champion_reference_raises(tmp_path: Path) -> None:
    store = SQLiteSSTStore(tmp_path / "events.db")
    store.append_event(
        SSTEvent(
            event_id="e_tree",
            tree_id="tree_dangle",
            kind=EventKind.TREE_CREATED,
            idempotency_key="init_tree_dangle",
            payload={"tree_id": "tree_dangle", "root_goal": "Goal", "root_node_id": "root_tree_dangle"},
        )
    )
    store.append_event(
        SSTEvent(
            event_id="e_done",
            tree_id="tree_dangle",
            kind=EventKind.SEARCH_COMPLETED,
            idempotency_key="completed_tree_dangle",
            payload={"termination_reason": "champion_found", "champion_node_id": "cand_missing", "budget": {}},
        )
    )

    try:
        get_search_result(store, "tree_dangle")
    except IncompleteSearchError as exc:
        assert "cand_missing" in exc.message
    else:
        raise AssertionError("expected IncompleteSearchError for a dangling champion reference")
