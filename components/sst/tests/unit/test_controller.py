"""Unit tests for Bounded Search Policy, Gateway invoke, and SST Controller."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from sst.core.contracts import TaskPacket
from sst.core.errors import UnpricedCostBudgetError
from sst.core.events import EventKind
from sst.core.models import AuDHDContextCapsule
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
from sst.search.policy import BudgetTracker, SearchPolicy
from sst.storage.store import SQLiteSSTStore


class FakeGateway(ModelGateway):
    """Deterministic fake gateway for testing search controller using invoke."""

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


def test_budget_tracker_violations() -> None:
    policy = SearchPolicy(max_iterations=5, max_token_budget=1000, max_time_seconds=10)
    tracker = BudgetTracker()

    assert tracker.check_budget(policy) is None

    tracker.tokens_consumed = 1500
    assert "Token budget exceeded" in (tracker.check_budget(policy) or "")

    tracker.tokens_consumed = 500
    tracker.elapsed_seconds = 15.0
    assert "Time budget exceeded" in (tracker.check_budget(policy) or "")

    tracker.elapsed_seconds = 5.0
    tracker.iterations_completed = 5
    assert "Maximum iterations reached" in (tracker.check_budget(policy) or "")


def test_search_controller_execution_and_events(tmp_path: Path) -> None:
    src_dir = tmp_path / "repo"
    src_dir.mkdir()
    (src_dir / "math_mod.py").write_text("def mul(a, b): return a + b\n", encoding="utf-8")
    (src_dir / "test_math.py").write_text("from math_mod import mul\nassert mul(3, 4) == 12\n", encoding="utf-8")

    task = TaskPacket(
        task_id="t_mul",
        goal="Implement correct multiplication",
        source_repo_root=str(src_dir),
        base_commit="c1",
        snapshot_hash="h1",
        allowed_paths=["math_mod.py"],
        acceptance_commands=["python test_math.py"],
    )

    db_path = tmp_path / "events.db"
    store = SQLiteSSTStore(db_path)
    custody = CandidateCustodyManager(base_worktree_dir=tmp_path / "worktrees")
    gateway = FakeGateway(code_to_return="def mul(a, b): return a * b\n")
    policy = SearchPolicy(max_iterations=2, branching_factor=1, max_depth=3)

    controller = SSTSearchController(
        task=task,
        gateway=gateway,
        store=store,
        custody_manager=custody,
        policy=policy,
    )

    tree_id = "tree_test_mul"
    champion = asyncio.run(controller.execute_search(tree_id))

    assert champion is not None
    assert champion.candidate_id.startswith("cand_tree_test_mul")
    assert champion.target_paths == ["math_mod.py"]
    assert "def mul(a, b): return a * b" in champion.patch_diff

    # Verify event stream
    events = store.get_events(tree_id)
    kinds = [e.kind for e in events]
    assert EventKind.TREE_CREATED in kinds
    assert EventKind.NODE_PROPOSED in kinds
    assert EventKind.VERIFIER_STARTED in kinds
    assert EventKind.VERIFIER_FINISHED in kinds
    assert EventKind.SCORE_RECORDED in kinds
    assert EventKind.PROMOTION_RECOMMENDED in kinds


def test_search_controller_critic_absence_fallback(tmp_path: Path) -> None:
    """Tests that search controller gracefully falls back to verifier scoring when critique route is absent."""
    src_dir = tmp_path / "repo"
    src_dir.mkdir()
    (src_dir / "math_mod.py").write_text("def mul(a, b): return a + b\n", encoding="utf-8")
    (src_dir / "test_math.py").write_text("from math_mod import mul\nassert mul(3, 4) == 12\n", encoding="utf-8")

    task = TaskPacket(
        task_id="t_fallback",
        goal="Implement correct multiplication",
        source_repo_root=str(src_dir),
        base_commit="c1",
        snapshot_hash="h1",
        allowed_paths=["math_mod.py"],
        acceptance_commands=["python test_math.py"],
    )

    db_path = tmp_path / "events_fallback.db"
    store = SQLiteSSTStore(db_path)
    custody = CandidateCustodyManager(base_worktree_dir=tmp_path / "worktrees")

    gateway = ModelGateway()
    prof = ProviderProfile(
        name="test-prof",
        kind=ProviderKind.TEST,
        api_base="test://",
        catalog=ModelCatalog(models=[ModelCatalogEntry(id="fake-model", display_label="Fake")]),
    )
    gateway.register_profile(prof)
    gateway.set_route("diverge", "test-prof", "fake-model")
    # Intentionally do NOT set 'critique' route
    gateway.invoke = lambda request: GatewayResponse(  # type: ignore[method-assign]
        content="def mul(a, b): return a * b\n",
        profile="test-prof",
        model="fake-model",
        prompt_tokens=30,
        completion_tokens=30,
        total_tokens=60,
        cost_usd=0.001,
    )

    policy = SearchPolicy(max_iterations=1, branching_factor=1, max_depth=2)
    controller = SSTSearchController(
        task=task,
        gateway=gateway,
        store=store,
        custody_manager=custody,
        policy=policy,
    )

    tree_id = "tree_fallback"
    champion = asyncio.run(controller.execute_search(tree_id))
    assert champion is not None
    assert "def mul(a, b): return a * b" in champion.patch_diff
    assert controller.budget_tracker.estimated_cost_usd > 0.0


def test_search_controller_budget_exhaustion(tmp_path: Path) -> None:
    """Tests that search controller halts when budget is exceeded and emits BUDGET_EXHAUSTED event."""
    src_dir = tmp_path / "repo"
    src_dir.mkdir()
    (src_dir / "math_mod.py").write_text("def mul(a, b): return a * b\n", encoding="utf-8")
    (src_dir / "test_math.py").write_text("from math_mod import mul\nassert mul(3, 4) == 12\n", encoding="utf-8")

    task = TaskPacket(
        task_id="t_budget",
        goal="Multiplication task",
        source_repo_root=str(src_dir),
        base_commit="c1",
        snapshot_hash="h1",
        allowed_paths=["math_mod.py"],
        acceptance_commands=["python test_math.py"],
    )

    db_path = tmp_path / "events_budget.db"
    store = SQLiteSSTStore(db_path)
    custody = CandidateCustodyManager(base_worktree_dir=tmp_path / "worktrees")
    gateway = FakeGateway(code_to_return="def mul(a, b): return a * b\n")

    # Policy with 0 token budget so it triggers violation immediately on iteration 1
    policy = SearchPolicy(max_iterations=5, branching_factor=1, max_token_budget=50)
    controller = SSTSearchController(
        task=task,
        gateway=gateway,
        store=store,
        custody_manager=custody,
        policy=policy,
    )

    tree_id = "tree_budget"
    asyncio.run(controller.execute_search(tree_id))

    events = store.get_events(tree_id)
    kinds = [e.kind for e in events]
    assert EventKind.BUDGET_EXHAUSTED in kinds


def test_search_controller_cancellation(tmp_path: Path) -> None:
    """Tests cooperative cancellation in search controller."""
    src_dir = tmp_path / "repo"
    src_dir.mkdir()

    task = TaskPacket(
        task_id="t_cancel",
        goal="Task to cancel",
        source_repo_root=str(src_dir),
        base_commit="c1",
        snapshot_hash="h1",
    )

    db_path = tmp_path / "events_cancel.db"
    store = SQLiteSSTStore(db_path)
    custody = CandidateCustodyManager(base_worktree_dir=tmp_path / "worktrees")
    gateway = FakeGateway(code_to_return="code")
    policy = SearchPolicy(max_iterations=10)

    controller = SSTSearchController(
        task=task,
        gateway=gateway,
        store=store,
        custody_manager=custody,
        policy=policy,
    )
    controller.cancel()

    tree_id = "tree_cancel"
    result = asyncio.run(controller.execute_search(tree_id))
    assert result is None


class DialecticMultiRoleGateway(ModelGateway):
    """Gateway supporting dialectic roles: diverge, refine, critique, and synthesize."""

    def __init__(self, diverge_code: str, refine_code: str, synth_code: str) -> None:
        super().__init__()
        prof = ProviderProfile(
            name="test-prof",
            kind=ProviderKind.TEST,
            api_base="test://",
            catalog=ModelCatalog(models=[ModelCatalogEntry(id="fake-model", display_label="Fake")]),
        )
        self.register_profile(prof)
        self.set_route("diverge", "test-prof", "fake-model")
        self.set_route("refine", "test-prof", "fake-model")
        self.set_route("critique", "test-prof", "fake-model")
        self.set_route("synthesize", "test-prof", "fake-model")

        self.diverge_code = diverge_code
        self.refine_code = refine_code
        self.synth_code = synth_code
        self.invoked_roles: list[str] = []
        self.invoked_temperatures: list[float] = []

    def invoke(self, request: GatewayRequest) -> GatewayResponse:
        self.invoked_roles.append(request.role)
        self.invoked_temperatures.append(request.temperature)

        if request.role == "diverge":
            content = json.dumps(
                {
                    "branches": [
                        {
                            "branch_index": 0,
                            "strategy_title": "Branch A (Fast Mult)",
                            "hypothesis_or_rationale": "Optimized multiplication",
                            "proposed_changes": self.diverge_code,
                        },
                        {
                            "branch_index": 1,
                            "strategy_title": "Branch B (Safe Mult)",
                            "hypothesis_or_rationale": "Defensive typed multiplication",
                            "proposed_changes": self.diverge_code.replace(
                                "mul", "mul_safe\ndef mul(a, b): return mul_safe(a, b)"
                            ),
                        },
                    ]
                }
            )
        elif request.role == "refine":
            content = json.dumps(
                {
                    "refined_title": "Refined ASD Solution",
                    "refactoring_notes": "Enforced strict AST typing and contracts",
                    "executable_content": self.refine_code,
                }
            )
        elif request.role == "synthesize":
            content = json.dumps(
                {
                    "synthesized_title": "Unified Dialectic Multiplier",
                    "synthesis_rationale": "Merged speed of Branch A with defensive safety of Branch B",
                    "executable_content": self.synth_code,
                }
            )
        elif request.role == "critique":
            content = json.dumps(
                {
                    "value_score": 0.95,
                    "verdict": "APPROVE",
                    "critique": "Outstanding architectural compliance and elegance",
                }
            )
        else:
            content = self.diverge_code

        return GatewayResponse(
            content=content,
            profile="test-prof",
            model="fake-model",
            prompt_tokens=40,
            completion_tokens=40,
            total_tokens=80,
            cost_usd=0.002,
        )


def test_dialectic_refine_and_synthesize_expansion(tmp_path: Path) -> None:
    """Verifies that SSTSearchController executes REFINE and SYNTHESIZE expansions."""
    src_dir = tmp_path / "repo"
    src_dir.mkdir()
    (src_dir / "math_mod.py").write_text("def mul(a, b): return a + b\n", encoding="utf-8")
    (src_dir / "test_math.py").write_text("from math_mod import mul\nassert mul(3, 4) == 12\n", encoding="utf-8")

    task = TaskPacket(
        task_id="t_dialectic",
        goal="Implement high performance and safe multiplication",
        source_repo_root=str(src_dir),
        base_commit="c1",
        snapshot_hash="h1",
        allowed_paths=["math_mod.py"],
        acceptance_commands=["python test_math.py"],
    )

    db_path = tmp_path / "events_dialectic.db"
    store = SQLiteSSTStore(db_path)
    custody = CandidateCustodyManager(base_worktree_dir=tmp_path / "worktrees")

    gateway = DialecticMultiRoleGateway(
        diverge_code="def mul(a, b): return a * b\n",
        refine_code="def mul(a: int, b: int) -> int:\n    return int(a * b)\n",
        synth_code='def mul(a: int, b: int) -> int:\n    """Unified high-speed safe multiplier."""\n    return a * b\n',
    )

    policy = SearchPolicy(
        max_iterations=3,
        branching_factor=2,
        max_depth=3,
        temperature_diverge=1.2,
        temperature_refine=0.05,
        temperature_synthesize=0.3,
    )

    controller = SSTSearchController(
        task=task,
        gateway=gateway,
        store=store,
        custody_manager=custody,
        policy=policy,
    )

    tree_id = "tree_dialectic_01"
    champion = asyncio.run(controller.execute_search(tree_id))

    assert champion is not None
    assert "def mul" in champion.patch_diff

    # Verify roles invoked
    assert "diverge" in gateway.invoked_roles
    assert "synthesize" in gateway.invoked_roles
    assert "critique" in gateway.invoked_roles

    # Verify event stream has SYNTHESIS_PROPOSED
    events = store.get_events(tree_id)
    kinds = [e.kind for e in events]
    assert EventKind.TREE_CREATED in kinds
    assert EventKind.NODE_PROPOSED in kinds
    assert EventKind.SYNTHESIS_PROPOSED in kinds
    assert EventKind.PROMOTION_RECOMMENDED in kinds

    # Verify synthesis event payload
    synth_evts = [e for e in events if e.kind == EventKind.SYNTHESIS_PROPOSED]
    assert len(synth_evts) >= 1
    assert len(synth_evts[0].payload["parent_ids"]) == 2


def test_human_decision_requested_on_uncertainty_and_deletions(tmp_path: Path) -> None:
    """Verifies that HUMAN_DECISION_REQUESTED events are emitted on destructive actions or Cortex uncertainty."""
    src_dir = tmp_path / "repo"
    src_dir.mkdir()
    (src_dir / "math_mod.py").write_text("def mul(a, b): return a + b\n", encoding="utf-8")
    (src_dir / "test_math.py").write_text("from math_mod import mul\nassert mul(3, 4) == 12\n", encoding="utf-8")

    task = TaskPacket(
        task_id="t_escalate",
        goal="Multiplication task with human escalation",
        source_repo_root=str(src_dir),
        base_commit="c1",
        snapshot_hash="h1",
        allowed_paths=["math_mod.py"],
        acceptance_commands=["python test_math.py"],
    )

    db_path = tmp_path / "events_escalate.db"
    store = SQLiteSSTStore(db_path)
    custody = CandidateCustodyManager(base_worktree_dir=tmp_path / "worktrees")

    gateway = ModelGateway()
    prof = ProviderProfile(
        name="test-prof",
        kind=ProviderKind.TEST,
        api_base="test://",
        catalog=ModelCatalog(models=[ModelCatalogEntry(id="fake-model", display_label="Fake")]),
    )
    gateway.register_profile(prof)
    gateway.set_route("diverge", "test-prof", "fake-model")
    gateway.set_route("critique", "test-prof", "fake-model")

    def fake_invoke(request: GatewayRequest) -> GatewayResponse:
        if request.role == "critique":
            content = json.dumps(
                {
                    "value_score": 0.50,
                    "verdict": "ESCALATE_HUMAN",
                    "rationale": "Irreversible architectural modification requires human oversight",
                }
            )
        else:
            content = "def mul(a, b): return a * b\n"
        return GatewayResponse(
            content=content,
            profile="test-prof",
            model="fake-model",
            prompt_tokens=20,
            completion_tokens=20,
            total_tokens=40,
        )

    gateway.invoke = fake_invoke  # type: ignore[method-assign]

    policy = SearchPolicy(max_iterations=1, branching_factor=1, max_depth=2)
    controller = SSTSearchController(
        task=task,
        gateway=gateway,
        store=store,
        custody_manager=custody,
        policy=policy,
    )

    tree_id = "tree_escalate"
    asyncio.run(controller.execute_search(tree_id))

    events = store.get_events(tree_id)
    kinds = [e.kind for e in events]
    assert EventKind.HUMAN_DECISION_REQUESTED in kinds

    escalate_ev = [e for e in events if e.kind == EventKind.HUMAN_DECISION_REQUESTED][0]
    assert escalate_ev.payload["verdict"] == "ESCALATE_HUMAN"
    assert "oversight" in escalate_ev.payload["reason"]


def test_clean_code_regex_extraction() -> None:
    text_with_fences = (
        "Here is the solution you requested:\n\n"
        "```python\n"
        "def solve():\n"
        "    return 42\n"
        "```\n\n"
        "Let me know if you need more help!"
    )
    cleaned = SSTSearchController._clean_code(text_with_fences)
    assert cleaned == "def solve():\n    return 42"

    text_generic_fence = "Sure, see below:\n```\nx = 10\ny = 20\n```"
    assert SSTSearchController._clean_code(text_generic_fence) == "x = 10\ny = 20"

    raw_code = "def foo():\n    pass"
    assert SSTSearchController._clean_code(raw_code) == "def foo():\n    pass"


def test_generate_divergent_candidate_immutability(tmp_path: Path) -> None:
    src_dir = tmp_path / "repo"
    src_dir.mkdir()
    (src_dir / "main.py").write_text("def solve(): pass\n", encoding="utf-8")

    task = TaskPacket(
        task_id="t_imm",
        goal="Test immutability",
        source_repo_root=str(src_dir),
        base_commit="c1",
        snapshot_hash="h1",
        allowed_paths=["main.py"],
    )

    gateway = FakeGateway(code_to_return="def solve(): return 100\n")
    store = SQLiteSSTStore(tmp_path / "events.db")
    custody = CandidateCustodyManager(base_worktree_dir=tmp_path / "worktrees")

    controller = SSTSearchController(
        task=task,
        gateway=gateway,
        store=store,
        custody_manager=custody,
    )

    prop = asyncio.run(
        controller._generate_divergent_candidate(
            tree_id="tree_imm",
            candidate_id="custom_cand_id_999",
            parent_id="root_node",
        )
    )

    assert prop is not None
    assert prop.candidate_id == "custom_cand_id_999"


class RecordingGateway(FakeGateway):
    """Fake gateway that records the requests it receives."""

    def __init__(self, code_to_return: str) -> None:
        super().__init__(code_to_return)
        self.seen: list[GatewayRequest] = []

    def invoke(self, request: GatewayRequest) -> GatewayResponse:
        self.seen.append(request)
        return super().invoke(request)


def _recording_controller(tmp_path: Path, policy: SearchPolicy) -> tuple[SSTSearchController, RecordingGateway]:
    src_dir = tmp_path / "repo"
    src_dir.mkdir(exist_ok=True)
    task = TaskPacket(
        task_id="t_tok",
        goal="Token cap probe",
        source_repo_root=str(src_dir),
        base_commit="c1",
        snapshot_hash="h1",
        allowed_paths=["main.py"],
    )
    gateway = RecordingGateway(code_to_return="{}")
    controller = SSTSearchController(
        task=task,
        gateway=gateway,
        store=SQLiteSSTStore(tmp_path / "events.db"),
        custody_manager=CandidateCustodyManager(base_worktree_dir=tmp_path / "worktrees"),
        policy=policy,
    )
    return controller, gateway


def test_role_max_tokens_default_and_override(tmp_path: Path) -> None:
    defaulted, _ = _recording_controller(tmp_path, SearchPolicy())
    assert defaulted._role_max_tokens(2048) == 2048
    assert defaulted._role_max_tokens(1024) == 1024
    overridden, _ = _recording_controller(tmp_path, SearchPolicy(response_max_tokens=8192))
    assert overridden._role_max_tokens(2048) == 8192
    assert overridden._role_max_tokens(1024) == 8192


def test_diverge_request_carries_policy_token_override(tmp_path: Path) -> None:
    controller, gateway = _recording_controller(tmp_path, SearchPolicy(response_max_tokens=8192))
    capsule = AuDHDContextCapsule(goal="Token cap probe")
    asyncio.run(
        controller._generate_divergent_candidates(tree_id="tree_tok", iteration=0, parent_id="root", capsule=capsule)
    )
    assert gateway.seen, "expected the diverge role to be invoked"
    assert gateway.seen[0].max_tokens == 8192


def test_diverge_request_keeps_role_default_without_override(tmp_path: Path) -> None:
    controller, gateway = _recording_controller(tmp_path, SearchPolicy())
    capsule = AuDHDContextCapsule(goal="Token cap probe")
    asyncio.run(
        controller._generate_divergent_candidates(tree_id="tree_tok", iteration=0, parent_id="root", capsule=capsule)
    )
    assert gateway.seen, "expected the diverge role to be invoked"
    assert gateway.seen[0].max_tokens == 2048


def test_cost_cap_defaults_to_none() -> None:
    assert SearchPolicy().max_cost_usd is None


class PricedGateway(FakeGateway):
    """Fake gateway returning valid cost accounting."""

    def invoke(self, request: GatewayRequest) -> GatewayResponse:
        base = super().invoke(request)
        return GatewayResponse(
            content=base.content,
            profile=base.profile,
            model=base.model,
            prompt_tokens=base.prompt_tokens,
            completion_tokens=base.completion_tokens,
            total_tokens=base.total_tokens,
            cost_usd=0.05,
            cost_known=True,
        )


def test_cost_cap_with_unpriced_responses_is_rejected(tmp_path: Path) -> None:
    controller, _ = _recording_controller(tmp_path, SearchPolicy(max_cost_usd=5.0))
    with pytest.raises(UnpricedCostBudgetError, match="no USD pricing"):
        asyncio.run(controller.execute_search("tree_unpriced"))


def test_cost_cap_with_priced_responses_accumulates(tmp_path: Path) -> None:
    src_dir = tmp_path / "repo"
    src_dir.mkdir(exist_ok=True)
    task = TaskPacket(
        task_id="t_priced",
        goal="Priced probe",
        source_repo_root=str(src_dir),
        base_commit="c1",
        snapshot_hash="h1",
        allowed_paths=["main.py"],
    )
    controller = SSTSearchController(
        task=task,
        gateway=PricedGateway(code_to_return="{}"),
        store=SQLiteSSTStore(tmp_path / "events.db"),
        custody_manager=CandidateCustodyManager(base_worktree_dir=tmp_path / "worktrees"),
        policy=SearchPolicy(max_cost_usd=5.0),
    )
    asyncio.run(controller.execute_search("tree_priced"))
    assert controller.budget_tracker.estimated_cost_usd > 0.0


def test_task_cost_cap_with_unpriced_responses_is_rejected(tmp_path: Path) -> None:
    controller, _ = _recording_controller(tmp_path, SearchPolicy())
    controller.task = controller.task.model_copy(update={"cost_budget_usd": 1.0})
    with pytest.raises(UnpricedCostBudgetError, match="no USD pricing"):
        asyncio.run(controller.execute_search("tree_task_cap"))
