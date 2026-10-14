"""Unit tests for the injectable executor seam and domain outcome feedback."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import ClassVar

import pytest

from sst.core.contracts import CandidateProposal, TaskPacket
from sst.core.events import EventKind, SSTEvent
from sst.core.models import DeterministicGateResult
from sst.gateway.contracts import (
    GatewayRequest,
    GatewayResponse,
    ModelCatalog,
    ModelCatalogEntry,
    ProviderKind,
    ProviderProfile,
)
from sst.gateway.gateway import ModelGateway
from sst.protocols.executor import EXECUTOR_PROTOCOL_VERSION, ExecutorProtocol
from sst.sandbox.custody import CandidateCustodyManager, PatchApplicationResult
from sst.sandbox.executor import ExecutorUnavailableError, bind_executor, resolve_executor
from sst.sandbox.outcomes import get_outcomes, is_outcome_event, report_outcome
from sst.search.controller import SSTSearchController
from sst.search.policy import SearchPolicy
from sst.storage.projection import DAGProjection
from sst.storage.store import SQLiteSSTStore


class FakeExecutor:
    """Minimal ExecutorProtocol implementation recording invocations."""

    executor_version: ClassVar[str] = EXECUTOR_PROTOCOL_VERSION

    def __init__(self, passed: bool = True) -> None:
        self.passed = passed
        self.apply_calls: list[str] = []
        self.verify_calls: list[str] = []

    def apply_proposal(
        self,
        proposal: CandidateProposal,
        workspace_dir: Path | str,
        task: TaskPacket | None = None,
    ) -> PatchApplicationResult:
        _ = (workspace_dir, task)
        self.apply_calls.append(proposal.candidate_id)
        return PatchApplicationResult(
            success=True,
            applied_files=list(proposal.target_paths),
            patch_hash="fake",
            post_patch_digest="fake",
        )

    def verify_candidate_proposal(
        self,
        task: TaskPacket,
        proposal: CandidateProposal,
        source_dir: Path | str,
        acceptance_command: str | None = None,
        timeout: int = 120,
    ) -> DeterministicGateResult:
        _ = (task, source_dir, acceptance_command, timeout)
        self.verify_calls.append(proposal.candidate_id)
        return DeterministicGateResult(
            passed=self.passed,
            exit_code=0 if self.passed else 1,
            stdout="fake run",
            stderr="" if self.passed else "fake failure",
            duration_seconds=0.01,
        )


class FakeGateway(ModelGateway):
    """Deterministic fake gateway returning fixed code and approving critiques."""

    def __init__(self, code_to_return: str) -> None:
        super().__init__()
        prof = ProviderProfile(
            name="test-prof",
            kind=ProviderKind.TEST,
            api_base="test://",
            catalog=ModelCatalog(models=[ModelCatalogEntry(id="fake-model", display_label="Fake")]),
        )
        self.register_profile(prof)
        self.set_route("diverge", "test-prof", "fake-model")
        self.set_route("critique", "test-prof", "fake-model")
        self.code_to_return = code_to_return

    def invoke(self, request: GatewayRequest) -> GatewayResponse:
        if request.role == "critique":
            content = '{"value_score": 0.95, "verdict": "APPROVE", "rationale": "High quality solution"}'
        else:
            content = self.code_to_return
        return GatewayResponse(
            content=content,
            profile="test-prof",
            model="fake-model",
            prompt_tokens=50,
            completion_tokens=50,
            total_tokens=100,
        )


def _make_task(src_dir: Path) -> TaskPacket:
    return TaskPacket(
        task_id="t_exec",
        goal="Implement correct multiplication",
        source_repo_root=str(src_dir),
        base_commit="c1",
        snapshot_hash="h1",
        allowed_paths=["math_mod.py"],
        acceptance_commands=["python test_math.py"],
    )


def _make_controller(tmp_path: Path, gateway: ModelGateway) -> SSTSearchController:
    src_dir = tmp_path / "repo"
    src_dir.mkdir(exist_ok=True)
    (src_dir / "math_mod.py").write_text("def mul(a, b): return a + b\n", encoding="utf-8")
    (src_dir / "test_math.py").write_text("from math_mod import mul\nassert mul(3, 4) == 12\n", encoding="utf-8")
    return SSTSearchController(
        task=_make_task(src_dir),
        gateway=gateway,
        store=SQLiteSSTStore(tmp_path / "events.db"),
        custody_manager=CandidateCustodyManager(base_worktree_dir=tmp_path / "worktrees"),
        policy=SearchPolicy(max_iterations=1, branching_factor=1, max_depth=2),
    )


def test_custody_manager_satisfies_executor_protocol() -> None:
    custody = CandidateCustodyManager(base_worktree_dir="/tmp/sst-exec-seam")
    assert isinstance(custody, ExecutorProtocol)
    assert custody.executor_version == EXECUTOR_PROTOCOL_VERSION


def test_custody_timeout_semantics_return_124(tmp_path: Path) -> None:
    custody = CandidateCustodyManager(base_worktree_dir=tmp_path / "worktrees")
    src_dir = tmp_path / "src_repo"
    src_dir.mkdir()
    (src_dir / "app.py").write_text("x = 1\n", encoding="utf-8")
    task = TaskPacket(
        task_id="t_timeout",
        goal="Timeout check",
        source_repo_root=str(src_dir),
        base_commit="c1",
        snapshot_hash="h1",
        allowed_paths=["app.py"],
    )
    proposal = CandidateProposal(
        candidate_id="cand_sleep",
        tree_id="tree_timeout",
        title="Sleep",
        rationale="Sleep past the timeout",
        target_paths=["app.py"],
        patch_diff="x = 2\n",
    )
    res = custody.verify_candidate_proposal(
        task=task,
        proposal=proposal,
        source_dir=src_dir,
        acceptance_command=f'"{sys.executable}" -c "import time; time.sleep(30)"',
        timeout=1,
    )
    assert res.passed is False
    assert res.exit_code == 124
    assert res.failure_reason is not None and "timeout" in res.failure_reason.lower()


def test_resolve_executor_defaults_to_custody_manager(tmp_path: Path) -> None:
    controller = _make_controller(tmp_path, FakeGateway("def mul(a, b): return a * b\n"))
    assert resolve_executor(controller) is controller.custody_manager


def test_bind_executor_validates_and_injects(tmp_path: Path) -> None:
    controller = _make_controller(tmp_path, FakeGateway("def mul(a, b): return a * b\n"))
    fake: ExecutorProtocol = FakeExecutor()
    assert isinstance(fake, ExecutorProtocol)
    bind_executor(controller, fake)
    assert controller.custody_manager is fake
    assert resolve_executor(controller) is fake


def test_bind_executor_rejects_non_protocol_object(tmp_path: Path) -> None:
    controller = _make_controller(tmp_path, FakeGateway("x = 1\n"))
    with pytest.raises(TypeError):
        bind_executor(controller, SimpleNamespace())  # type: ignore[arg-type]


def test_resolve_executor_override_wins(tmp_path: Path) -> None:
    controller = _make_controller(tmp_path, FakeGateway("x = 1\n"))
    default_executor = resolve_executor(controller)
    override = FakeExecutor()
    assert resolve_executor(controller, override=override) is override
    assert resolve_executor(controller) is default_executor


def test_resolve_executor_prefers_native_executor_slot() -> None:
    native = FakeExecutor()
    holder = SimpleNamespace(executor=native, custody_manager=FakeExecutor())
    assert resolve_executor(holder) is native


def test_resolve_executor_raises_when_absent() -> None:
    with pytest.raises(ExecutorUnavailableError):
        resolve_executor(SimpleNamespace())


def test_execute_search_uses_injected_fake_executor(tmp_path: Path) -> None:
    controller = _make_controller(tmp_path, FakeGateway("def mul(a, b): return a * b\n"))
    fake = FakeExecutor(passed=True)
    bind_executor(controller, fake)

    champion = asyncio.run(controller.execute_search("tree_fake_exec"))

    assert champion is not None
    assert fake.verify_calls, "injected executor must service verification"
    assert all(cid.startswith("cand_tree_fake_exec") for cid in fake.verify_calls)


def test_execute_search_with_failing_fake_executor_yields_no_champion(tmp_path: Path) -> None:
    controller = _make_controller(tmp_path, FakeGateway("def mul(a, b): return a * b\n"))
    fake = FakeExecutor(passed=False)
    bind_executor(controller, fake)

    champion = asyncio.run(controller.execute_search("tree_fake_fail"))

    assert champion is None
    assert fake.verify_calls
    kinds = [e.kind for e in controller.store.get_events("tree_fake_fail")]
    assert EventKind.VERIFIER_FINISHED in kinds
    assert EventKind.PROMOTION_RECOMMENDED not in kinds


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


def test_report_outcome_records_attributable_verbatim_event(tmp_path: Path) -> None:
    store = SQLiteSSTStore(tmp_path / "outcomes.db")
    _seed_proposed_candidate(store, "tree_out", "cand_1")

    seq = report_outcome(
        store,
        tree_id="tree_out",
        candidate_id="cand_1",
        verdict="ROLLED_BACK_IN_PROD",
        evidence_refs=["deploy-log:42", "incident:7"],
        actor="deploy-pipeline",
        note="Latency regression",
    )

    assert seq > 0
    outcomes = get_outcomes(store, "tree_out")
    assert len(outcomes) == 1
    evt = outcomes[0]
    assert evt.node_id == "cand_1"
    assert evt.actor == "deploy-pipeline"
    assert evt.payload["domain_verdict"] == "ROLLED_BACK_IN_PROD"
    assert evt.payload["evidence_refs"] == ["deploy-log:42", "incident:7"]
    assert evt.payload["note"] == "Latency regression"
    assert evt.payload["sst_authoritative"] is False
    assert is_outcome_event(evt) is True


def test_report_outcome_rejects_empty_attribution(tmp_path: Path) -> None:
    store = SQLiteSSTStore(tmp_path / "outcomes.db")
    with pytest.raises(ValueError):
        report_outcome(store, tree_id="t", candidate_id="c", verdict="  ", actor="a")
    with pytest.raises(ValueError):
        report_outcome(store, tree_id="t", candidate_id="c", verdict="OK", actor="")
    with pytest.raises(ValueError):
        report_outcome(store, tree_id="t", candidate_id="", verdict="OK", actor="a")


def test_report_outcome_is_idempotent(tmp_path: Path) -> None:
    store = SQLiteSSTStore(tmp_path / "outcomes.db")
    _seed_proposed_candidate(store, "tree_out", "cand_1")
    first = report_outcome(
        store,
        tree_id="tree_out",
        candidate_id="cand_1",
        verdict="OK",
        actor="op",
        idempotency_key="outcome_once",
    )
    second = report_outcome(
        store,
        tree_id="tree_out",
        candidate_id="cand_1",
        verdict="OK",
        actor="op",
        idempotency_key="outcome_once",
    )
    assert first == second
    assert len(get_outcomes(store, "tree_out")) == 1


def test_report_outcome_never_overrides_projection(tmp_path: Path) -> None:
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
        report_outcome(
            store,
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


def test_is_outcome_event_ignores_regular_events(tmp_path: Path) -> None:
    store = SQLiteSSTStore(tmp_path / "outcomes.db")
    _seed_proposed_candidate(store, "tree_out", "cand_1")
    for evt in store.get_events("tree_out"):
        assert is_outcome_event(evt) is False
    assert get_outcomes(store, "tree_out") == []
