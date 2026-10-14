"""Unit tests for the run_search result envelope and failure/budget/termination visibility (B1)."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from pathlib import Path

import pytest
from pydantic import ValidationError

from sst.core.contracts import SearchResult, TaskPacket, TerminationReason
from sst.core.events import EventKind
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
from sst.storage.store import SQLiteSSTStore

GOOD_CODE = "def mul(a, b): return a * b\n"
BAD_CODE = "def mul(a, b): return a + b\n"


class RoleFailingGateway(ModelGateway):
    """Deterministic gateway that fails selected roles with a categorized gateway error."""

    def __init__(
        self,
        *,
        fail_roles: set[str] | None = None,
        diverge_code: str = GOOD_CODE,
        branch_count: int = 1,
    ) -> None:
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
        self.branch_count = branch_count
        self.hook: Callable[[], None] | None = None
        self._hooked = False

    def invoke(self, request: GatewayRequest) -> GatewayResponse:
        if request.role in self.fail_roles:
            raise UnreachableEndpointError("Cannot connect to test provider", profile="test-prof")
        if request.role == "diverge" and self.hook is not None and not self._hooked:
            self._hooked = True
            self.hook()
        if request.role == "critique":
            content = '{"value_score": 0.95, "verdict": "APPROVE", "rationale": "High quality solution"}'
        elif request.role == "refine":
            content = json.dumps(
                {
                    "refined_title": "Refined solution",
                    "refactoring_notes": "Strict typing",
                    "executable_content": GOOD_CODE,
                }
            )
        elif request.role == "synthesize":
            content = json.dumps(
                {
                    "synthesized_title": "Unified solution",
                    "synthesis_rationale": "Blend of strengths",
                    "executable_content": GOOD_CODE,
                }
            )
        elif self.branch_count > 1:
            content = json.dumps(
                {
                    "branches": [
                        {
                            "branch_index": i,
                            "strategy_title": f"Branch {i}",
                            "hypothesis_or_rationale": "Divergent exploration",
                            "proposed_changes": self.diverge_code,
                        }
                        for i in range(self.branch_count)
                    ]
                }
            )
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


def _make_controller(
    tmp_path: Path,
    gateway: ModelGateway,
    policy: SearchPolicy,
    task_id: str = "t_env",
) -> SSTSearchController:
    src_dir = tmp_path / "repo"
    src_dir.mkdir(exist_ok=True)
    (src_dir / "math_mod.py").write_text("def mul(a, b): return a + b\n", encoding="utf-8")
    (src_dir / "test_math.py").write_text("from math_mod import mul\nassert mul(3, 4) == 12\n", encoding="utf-8")
    task = TaskPacket(
        task_id=task_id,
        goal="Implement correct multiplication",
        source_repo_root=str(src_dir),
        base_commit="c1",
        snapshot_hash="h1",
        allowed_paths=["math_mod.py"],
        acceptance_commands=["python test_math.py"],
    )
    store = SQLiteSSTStore(tmp_path / f"events_{task_id}.db")
    custody = CandidateCustodyManager(base_worktree_dir=tmp_path / "worktrees")
    return SSTSearchController(
        task=task,
        gateway=gateway,
        store=store,
        custody_manager=custody,
        policy=policy,
    )


def test_run_search_envelope_shape(tmp_path: Path) -> None:
    gateway = RoleFailingGateway()
    policy = SearchPolicy(max_iterations=2, branching_factor=1, max_depth=3)
    controller = _make_controller(tmp_path, gateway, policy)

    result = asyncio.run(controller.run_search("tree_env"))

    assert isinstance(result, SearchResult)
    assert result.tree_id == "tree_env"
    assert result.termination_reason is TerminationReason.CHAMPION_FOUND
    assert result.champion is not None
    assert "def mul(a, b): return a * b" in result.champion.patch_diff

    assert len(result.alternatives) >= 1
    assert result.alternatives[0].candidate.candidate_id == result.champion.candidate_id
    for alt in result.alternatives:
        assert alt.verifier_outcome is not None
        assert alt.verifier_outcome.passed is True
        assert alt.score is not None
        assert alt.evidence_refs, "each alternative must carry event evidence refs"

    assert result.budget_consumed.tokens_consumed > 0
    assert result.budget_consumed.iterations_completed == 2
    assert result.budget_consumed.elapsed_seconds >= 0.0
    assert result.provider_errors == []
    assert result.event_log_ref.startswith("sqlite:")
    assert "tree_env" in result.event_log_ref

    # Legacy tracker loop-top stamp semantics are frozen (STC INFO-2 pins this).
    assert controller.budget_tracker.iterations_completed == 1

    events = controller.store.get_events("tree_env")
    assert events[-1].kind is EventKind.SEARCH_COMPLETED
    assert events[-1].payload["termination_reason"] == TerminationReason.CHAMPION_FOUND.value

    with pytest.raises(ValidationError):
        result.tree_id = "mutated"


def test_provider_error_diverge_records_event_and_envelope(tmp_path: Path) -> None:
    gateway = RoleFailingGateway(fail_roles={"diverge"})
    policy = SearchPolicy(max_iterations=2, branching_factor=1, max_depth=3)
    controller = _make_controller(tmp_path, gateway, policy)

    result = asyncio.run(controller.run_search("tree_diverge_fail"))

    assert result.termination_reason is TerminationReason.NO_CANDIDATE
    assert result.champion is None
    assert result.alternatives == []
    assert len(result.provider_errors) == 2
    for record in result.provider_errors:
        assert record.role == "diverge"
        assert record.category == "unreachable_endpoint"
        assert "Ollama" in record.remediation
        assert record.iteration in (0, 1)

    events = controller.store.get_events("tree_diverge_fail")
    err_events = [e for e in events if e.kind is EventKind.PROVIDER_ERROR]
    assert len(err_events) == 2
    assert err_events[0].payload["category"] == "unreachable_endpoint"
    assert "Ollama" in err_events[0].payload["remediation"]
    completed = [e for e in events if e.kind is EventKind.SEARCH_COMPLETED][0]
    assert completed.payload["provider_error_count"] == 2
    assert events[-1].kind is EventKind.SEARCH_COMPLETED


def test_provider_error_critique_falls_back_with_visibility(tmp_path: Path) -> None:
    gateway = RoleFailingGateway(fail_roles={"critique"})
    policy = SearchPolicy(max_iterations=1, branching_factor=1, max_depth=2)
    controller = _make_controller(tmp_path, gateway, policy)

    result = asyncio.run(controller.run_search("tree_critique_fail"))

    # Fallback verifier-based scoring still yields a champion, now visibly.
    assert result.champion is not None
    assert result.termination_reason is TerminationReason.CHAMPION_FOUND
    assert len(result.provider_errors) == 1
    assert result.provider_errors[0].role == "critique"
    assert result.provider_errors[0].category == "unreachable_endpoint"

    events = controller.store.get_events("tree_critique_fail")
    err_events = [e for e in events if e.kind is EventKind.PROVIDER_ERROR]
    assert len(err_events) == 1
    assert err_events[0].payload["role"] == "critique"
    assert err_events[0].node_id == result.champion.candidate_id
    score_events = [e for e in events if e.kind is EventKind.SCORE_RECORDED]
    assert score_events[0].payload["verdict"] == "CRITIQUE_FAILED"
    assert "No semantic approval" in score_events[0].payload["critique"]


def test_provider_error_refine_and_synthesize_visible(tmp_path: Path) -> None:
    gateway = RoleFailingGateway(fail_roles={"refine", "synthesize"}, branch_count=2)
    policy = SearchPolicy(max_iterations=3, branching_factor=2, max_depth=3)
    controller = _make_controller(tmp_path, gateway, policy)

    result = asyncio.run(controller.run_search("tree_ref_synth_fail"))

    assert result.champion is not None
    assert "def mul(a, b): return a * b" in result.champion.patch_diff
    roles = {record.role for record in result.provider_errors}
    assert roles == {"refine", "synthesize"}

    events = controller.store.get_events("tree_ref_synth_fail")
    err_roles = {e.payload["role"] for e in events if e.kind is EventKind.PROVIDER_ERROR}
    assert err_roles == {"refine", "synthesize"}


def test_cancel_before_start(tmp_path: Path) -> None:
    gateway = RoleFailingGateway()
    policy = SearchPolicy(max_iterations=3, branching_factor=1, max_depth=3)
    controller = _make_controller(tmp_path, gateway, policy)
    controller.cancel()

    result = asyncio.run(controller.run_search("tree_cancel_early"))

    assert result.termination_reason is TerminationReason.CANCELLED
    assert result.champion is None
    assert result.alternatives == []
    assert result.budget_consumed.iterations_completed == 0

    events = controller.store.get_events("tree_cancel_early")
    kinds = [e.kind for e in events]
    assert EventKind.SEARCH_CANCELLED in kinds
    assert events[-1].kind is EventKind.SEARCH_COMPLETED
    assert events[-1].payload["termination_reason"] == TerminationReason.CANCELLED.value
    cancelled = [e for e in events if e.kind is EventKind.SEARCH_CANCELLED][0]
    assert cancelled.payload["iterations_completed"] == 0


def test_cancel_mid_run_preserves_champion(tmp_path: Path) -> None:
    gateway = RoleFailingGateway()
    policy = SearchPolicy(max_iterations=3, branching_factor=1, max_depth=3)
    controller = _make_controller(tmp_path, gateway, policy)
    gateway.hook = controller.cancel

    result = asyncio.run(controller.run_search("tree_cancel_mid"))

    assert result.termination_reason is TerminationReason.CANCELLED
    assert result.champion is not None
    assert "def mul(a, b): return a * b" in result.champion.patch_diff

    events = controller.store.get_events("tree_cancel_mid")
    kinds = [e.kind for e in events]
    assert EventKind.SEARCH_CANCELLED in kinds
    assert events[-1].kind is EventKind.SEARCH_COMPLETED
    assert events[-1].payload["termination_reason"] == TerminationReason.CANCELLED.value


def test_execute_search_returns_envelope_champion(tmp_path: Path) -> None:
    gateway = RoleFailingGateway()
    policy = SearchPolicy(max_iterations=1, branching_factor=1, max_depth=2)
    controller = _make_controller(tmp_path, gateway, policy)

    champion = asyncio.run(controller.execute_search("tree_eq_a"))
    result = asyncio.run(controller.run_search("tree_eq_b"))

    assert champion is not None
    assert result.champion is not None
    assert champion.patch_diff == result.champion.patch_diff
    assert champion.role == result.champion.role == "DIVERGE"


def test_budget_exhaustion_termination_reason(tmp_path: Path) -> None:
    gateway = RoleFailingGateway()
    policy = SearchPolicy(max_iterations=5, branching_factor=1, max_token_budget=50)
    controller = _make_controller(tmp_path, gateway, policy)

    result = asyncio.run(controller.run_search("tree_budget_env"))

    assert result.termination_reason is TerminationReason.BUDGET_EXHAUSTED
    assert result.champion is not None

    events = controller.store.get_events("tree_budget_env")
    kinds = [e.kind for e in events]
    assert EventKind.BUDGET_EXHAUSTED in kinds
    assert events[-1].kind is EventKind.SEARCH_COMPLETED
    completed = [e for e in events if e.kind is EventKind.SEARCH_COMPLETED][0]
    assert "Token budget exceeded" in (completed.payload["budget_violation"] or "")


def test_no_candidate_includes_failed_verifier_outcomes(tmp_path: Path) -> None:
    gateway = RoleFailingGateway(diverge_code=BAD_CODE)
    policy = SearchPolicy(max_iterations=1, branching_factor=1, max_depth=2)
    controller = _make_controller(tmp_path, gateway, policy)

    result = asyncio.run(controller.run_search("tree_no_champ"))

    assert result.termination_reason is TerminationReason.NO_CANDIDATE
    assert result.champion is None
    assert len(result.alternatives) == 1
    alt = result.alternatives[0]
    assert alt.score is None
    assert alt.verifier_outcome is not None
    assert alt.verifier_outcome.passed is False
    assert alt.evidence_refs, "failed candidates must still carry evidence refs"

    events = controller.store.get_events("tree_no_champ")
    assert events[-1].kind is EventKind.SEARCH_COMPLETED
