"""Wave-2 wiring tests: native executor slot (REQUEST-1), TREE_CREATED memory
fragment (REQUEST-3), and capsule-model provenance fields (REQUEST-4)."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import ClassVar

from sst.context.capsule import ContextCapsuleCompiler
from sst.context.memory_adapter import StaticMemoryProvider
from sst.core.contracts import CandidateProposal, TaskPacket
from sst.core.events import EventKind
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
from sst.protocols.executor import ExecutorProtocol
from sst.sandbox.custody import CandidateCustodyManager, PatchApplicationResult
from sst.search.controller import SSTSearchController
from sst.search.policy import SearchPolicy
from sst.storage.store import SQLiteSSTStore

GOOD_CODE = "def mul(a, b): return a * b\n"


class FakeExecutor:
    """Minimal ExecutorProtocol implementation recording invocations."""

    executor_version: ClassVar[str] = "executor/v1"

    def __init__(self, passed: bool = True) -> None:
        self.passed = passed
        self.verify_calls: list[str] = []

    def apply_proposal(
        self,
        proposal: CandidateProposal,
        workspace_dir: Path | str,
        task: TaskPacket | None = None,
    ) -> PatchApplicationResult:
        _ = (workspace_dir, task)
        return PatchApplicationResult(success=True, applied_files=list(proposal.target_paths))

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
        return DeterministicGateResult(passed=self.passed, exit_code=0 if self.passed else 1)


class BranchGateway(ModelGateway):
    """Gateway returning N divergent branches and approving critiques."""

    def __init__(self, branch_count: int = 1) -> None:
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
        self.branch_count = branch_count

    def invoke(self, request: GatewayRequest) -> GatewayResponse:
        if request.role == "critique":
            content = '{"value_score": 0.95, "verdict": "APPROVE", "rationale": "High quality"}'
        elif request.role == "synthesize":
            content = json.dumps(
                {
                    "synthesized_title": "Unified",
                    "synthesis_rationale": "Blend",
                    "executable_content": GOOD_CODE,
                }
            )
        elif request.role == "refine":
            content = json.dumps(
                {
                    "refined_title": "Refined",
                    "refactoring_notes": "Notes",
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
                            "hypothesis_or_rationale": "Explore",
                            "proposed_changes": GOOD_CODE,
                        }
                        for i in range(self.branch_count)
                    ]
                }
            )
        else:
            content = GOOD_CODE
        return GatewayResponse(
            content=content,
            profile="test-prof",
            model="fake-model",
            prompt_tokens=10,
            completion_tokens=10,
            total_tokens=20,
        )


def _make_controller(
    tmp_path: Path,
    gateway: ModelGateway,
    executor: ExecutorProtocol | None = None,
    memory_provider: StaticMemoryProvider | None = None,
) -> SSTSearchController:
    src_dir = tmp_path / "repo"
    src_dir.mkdir(exist_ok=True)
    (src_dir / "math_mod.py").write_text("def mul(a, b): return a + b\n", encoding="utf-8")
    (src_dir / "test_math.py").write_text("from math_mod import mul\nassert mul(3, 4) == 12\n", encoding="utf-8")
    task = TaskPacket(
        task_id="t_wire",
        goal="Implement correct multiplication",
        source_repo_root=str(src_dir),
        base_commit="c1",
        snapshot_hash="h1",
        allowed_paths=["math_mod.py"],
        acceptance_commands=["python test_math.py"],
    )
    compiler = ContextCapsuleCompiler(workspace_root=src_dir, memory_provider=memory_provider)
    return SSTSearchController(
        task=task,
        gateway=gateway,
        store=SQLiteSSTStore(tmp_path / "events.db"),
        custody_manager=CandidateCustodyManager(base_worktree_dir=tmp_path / "worktrees"),
        policy=SearchPolicy(max_iterations=2, branching_factor=2, max_depth=3),
        capsule_compiler=compiler,
        executor=executor,
    )


def test_executor_ctor_defaults_to_custody_manager(tmp_path: Path) -> None:
    controller = _make_controller(tmp_path, BranchGateway())
    assert controller.executor is controller.custody_manager
    assert isinstance(controller.executor, ExecutorProtocol)


def test_executor_ctor_injection_services_verification(tmp_path: Path) -> None:
    fake = FakeExecutor(passed=True)
    assert isinstance(fake, ExecutorProtocol)
    controller = _make_controller(tmp_path, BranchGateway(), executor=fake)

    champion = asyncio.run(controller.execute_search("tree_ctor_exec"))

    assert champion is not None
    assert fake.verify_calls, "injected ctor executor must service verification"
    assert controller.executor is fake


def test_executor_ctor_injection_covers_synthesis_site(tmp_path: Path) -> None:
    """Two high-scoring branches trigger synthesis; its verify call must also use the injected executor."""
    fake = FakeExecutor(passed=True)
    controller = _make_controller(tmp_path, BranchGateway(branch_count=2), executor=fake)

    champion = asyncio.run(controller.execute_search("tree_ctor_synth"))

    assert champion is not None
    kinds = [e.kind for e in controller.store.get_events("tree_ctor_synth")]
    assert EventKind.SYNTHESIS_PROPOSED in kinds
    assert any("_synth_" in cid for cid in fake.verify_calls)


def test_tree_created_carries_memory_fragment_default(tmp_path: Path) -> None:
    controller = _make_controller(tmp_path, BranchGateway())
    asyncio.run(controller.execute_search("tree_mem_default"))

    created = next(e for e in controller.store.get_events("tree_mem_default") if e.kind is EventKind.TREE_CREATED)
    for key in (
        "memory_provider",
        "memory_availability",
        "memory_adapter_version",
        "memory_evidence_refs",
        "memory_insight_provenance",
        "memory_insight_count",
        "memory_last_error",
    ):
        assert key in created.payload, f"TREE_CREATED must carry fragment key {key}"
    assert created.payload["memory_provider"] == "none"


def test_tree_created_carries_static_provider_fragment(tmp_path: Path) -> None:
    provider = StaticMemoryProvider(insights=["prefer pure functions"])
    controller = _make_controller(tmp_path, BranchGateway(), memory_provider=provider)
    asyncio.run(controller.execute_search("tree_mem_static"))

    created = next(e for e in controller.store.get_events("tree_mem_static") if e.kind is EventKind.TREE_CREATED)
    assert created.payload["memory_provider"] == "static"
    assert created.payload["memory_availability"] == "AVAILABLE"
    assert created.payload["memory_insight_count"] == 1
    assert created.payload["memory_evidence_refs"] == ["static:0"]


def test_capsule_model_carries_memory_provenance(tmp_path: Path) -> None:
    """REQUEST-4: the capsule model itself carries provenance from last_report."""
    src_dir = tmp_path / "repo"
    src_dir.mkdir()

    default_capsule = ContextCapsuleCompiler(workspace_root=src_dir).compile(goal="g")
    assert default_capsule.memory_provider == "none"
    assert default_capsule.memory_availability == "UNAVAILABLE"
    assert default_capsule.memory_evidence_refs == []

    static_capsule = ContextCapsuleCompiler(
        workspace_root=src_dir, memory_provider=StaticMemoryProvider(insights=["i1", "i2"])
    ).compile(goal="g")
    assert static_capsule.memory_provider == "static"
    assert static_capsule.memory_availability == "AVAILABLE"
    assert static_capsule.memory_evidence_refs == ["static:0", "static:1"]
