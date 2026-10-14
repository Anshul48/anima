"""Coordinator truthfulness reproductions: misleading-success gaps must fail here first.

R1: empty acceptance list must not yield an unqualified verified PASS.
R2: every acceptance command must run; a later failure must fail the gate.
R3: failed or malformed critique must not fabricate semantic APPROVE.
R4: provider/mode identity must be visible in the SearchResult envelope.
R5: TaskPacket budgets must bind the run (precedence over/with policy caps).
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from sst.context.capsule import ContextCapsuleCompiler
from sst.core.contracts import CandidateProposal, TaskPacket, TerminationReason
from sst.gateway.contracts import (
    GatewayRequest,
    GatewayResponse,
    ModelCatalog,
    ModelCatalogEntry,
    ProviderKind,
    ProviderProfile,
)
from sst.gateway.gateway import ModelGateway
from sst.sandbox.custody import CandidateCustodyManager
from sst.search.controller import SSTSearchController
from sst.search.policy import SearchPolicy
from sst.storage.store import SQLiteSSTStore


def _task(tmp_path: Path, **overrides: object) -> TaskPacket:
    fields: dict[str, object] = {
        "task_id": "task_repro",
        "goal": "repro goal",
        "source_repo_root": str(tmp_path),
        "base_commit": "abc123",
        "snapshot_hash": "snap",
    }
    fields.update(overrides)
    return TaskPacket(**fields)  # type: ignore[arg-type]


def _proposal() -> CandidateProposal:
    return CandidateProposal(
        candidate_id="cand_repro",
        tree_id="tree_repro",
        title="repro",
        rationale="repro",
        target_paths=["main.py"],
        patch_diff="print('hi')\n",
    )


def test_r1_empty_acceptance_is_not_verified(tmp_path: Path) -> None:
    custody = CandidateCustodyManager(base_worktree_dir=tmp_path / "ws")
    res = custody.verify_candidate_proposal(
        task=_task(tmp_path, acceptance_commands=[]),
        proposal=_proposal(),
        source_dir=tmp_path,
    )
    assert res.passed is False
    assert res.failure_reason is not None and "acceptance" in res.failure_reason.lower()


def test_r2_all_acceptance_commands_run(tmp_path: Path) -> None:
    custody = CandidateCustodyManager(base_worktree_dir=tmp_path / "ws")
    res = custody.verify_candidate_proposal(
        task=_task(tmp_path, acceptance_commands=["python -c 'pass'", "python -c 'raise SystemExit(1)'"]),
        proposal=_proposal(),
        source_dir=tmp_path,
    )
    assert res.passed is False


class _CritiqueFailsGateway(ModelGateway):
    def invoke(self, request: GatewayRequest) -> GatewayResponse:
        if request.role == "critique":
            raise _CritiqueBoom("critique endpoint down")
        return super().invoke(request)


class _CritiqueBoom(Exception):
    pass


def _test_gateway() -> ModelGateway:
    gateway = ModelGateway()
    gateway.register_profile(
        ProviderProfile(
            name="default",
            kind=ProviderKind.TEST,
            api_base="https://example.test/v1",
            selected_model="test-model",
            catalog=ModelCatalog(models=[ModelCatalogEntry(id="test-model", display_label="Test")]),
        )
    )
    return gateway


def _controller(tmp_path: Path, task: TaskPacket, gateway: ModelGateway) -> SSTSearchController:
    store = SQLiteSSTStore(tmp_path / "repro.db")
    custody = CandidateCustodyManager(base_worktree_dir=tmp_path / "ws")
    capsule = ContextCapsuleCompiler(workspace_root=tmp_path)
    return SSTSearchController(
        task=task,
        gateway=gateway,
        store=store,
        custody_manager=custody,
        policy=SearchPolicy(max_iterations=2),
        capsule_compiler=capsule,
    )


def test_r3_failed_critique_is_not_approve(tmp_path: Path) -> None:
    gateway = _CritiqueFailsGateway()
    gateway.register_profile(_test_gateway().get_profile("default"))  # type: ignore[arg-type]
    task = _task(tmp_path, acceptance_commands=["python -c 'pass'"])
    controller = _controller(tmp_path, task, gateway)
    result = asyncio.run(controller.run_search("tree_r3"))
    assert result.alternatives, "expected evaluated alternatives"
    assert result.provider_errors, "expected recorded provider error"
    assert result.alternatives[0].score is not None
    assert result.alternatives[0].score.critic_verdict != "APPROVE"


def test_r4_envelope_exposes_provider_identity(tmp_path: Path) -> None:
    controller = _controller(tmp_path, _task(tmp_path), _test_gateway())
    result = asyncio.run(controller.run_search("tree_r4"))
    assert '"TEST"' in result.model_dump_json()


def test_r5_task_token_budget_binds_run(tmp_path: Path) -> None:
    controller = _controller(tmp_path, _task(tmp_path, token_budget=1), _test_gateway())
    result = asyncio.run(controller.run_search("tree_r5"))
    assert result.termination_reason is TerminationReason.BUDGET_EXHAUSTED


def test_foreign_profile_shapes_degrade_to_unknown(tmp_path: Path) -> None:
    """Caller gateways may stuff non-ProviderProfile values (STC ScriptGateway).

    Binding introspection must degrade to UNKNOWN, never raise.
    """

    class _ForeignGateway(ModelGateway):
        def invoke(self, request: GatewayRequest) -> GatewayResponse:
            return GatewayResponse(content="x = 1\n", profile="test", model="script")

    gateway = _ForeignGateway()
    gateway.profiles["test"] = "test"  # type: ignore[assignment]
    controller = _controller(tmp_path, _task(tmp_path, acceptance_commands=["python -c 'pass'"]), gateway)
    result = asyncio.run(controller.run_search("tree_foreign"))
    assert result.gateway_bindings
    assert result.gateway_bindings[0].kind == "UNKNOWN"
