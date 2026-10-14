"""Wave-2 lease-guard tests: optional single-writer enforcement (default OFF)."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

from sst.core.contracts import TaskPacket
from sst.core.errors import LeaseAcquisitionError
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


class FakeGateway(ModelGateway):
    def __init__(self) -> None:
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

    def invoke(self, request: GatewayRequest) -> GatewayResponse:
        if request.role == "critique":
            content = '{"value_score": 0.95, "verdict": "APPROVE", "rationale": "High quality"}'
        else:
            content = "x = 1\n"
        return GatewayResponse(
            content=content,
            profile="test-prof",
            model="fake-model",
            prompt_tokens=10,
            completion_tokens=10,
            total_tokens=20,
        )


def _make_controller(tmp_path: Path, policy: SearchPolicy) -> SSTSearchController:
    src_dir = tmp_path / "repo"
    src_dir.mkdir(exist_ok=True)
    task = TaskPacket(
        task_id="t_lease",
        goal="Trivial task",
        source_repo_root=str(src_dir),
        base_commit="c1",
        snapshot_hash="h1",
        acceptance_commands=[f'{sys.executable} -c "pass"'],
    )
    return SSTSearchController(
        task=task,
        gateway=FakeGateway(),
        store=SQLiteSSTStore(tmp_path / "events.db"),
        custody_manager=CandidateCustodyManager(base_worktree_dir=tmp_path / "worktrees"),
        policy=policy,
    )


def test_lease_guard_off_by_default(tmp_path: Path) -> None:
    assert SearchPolicy().require_lease is False

    controller = _make_controller(tmp_path, SearchPolicy(max_iterations=1, branching_factor=1, max_depth=2))
    result = asyncio.run(controller.run_search("tree_unguarded"))

    assert result.champion is not None
    # No lease was held: another owner can acquire immediately.
    assert controller.store.acquire_lease("tree_unguarded", "other-owner") is True


def test_policy_require_lease_acquires_and_releases(tmp_path: Path) -> None:
    controller = _make_controller(
        tmp_path, SearchPolicy(max_iterations=1, branching_factor=1, max_depth=2, require_lease=True)
    )
    result = asyncio.run(controller.run_search("tree_guarded"))

    assert result.champion is not None
    # Released at run end: another owner can acquire immediately.
    assert controller.store.acquire_lease("tree_guarded", "other-owner") is True


def test_run_search_acquire_lease_override(tmp_path: Path) -> None:
    controller = _make_controller(tmp_path, SearchPolicy(max_iterations=1, branching_factor=1, max_depth=2))

    result = asyncio.run(controller.run_search("tree_override", acquire_lease=True))
    assert result.champion is not None
    assert controller.store.acquire_lease("tree_override", "other-owner") is True

    # Explicit False wins over a requiring policy.
    controller.policy.require_lease = True
    assert controller.store.acquire_lease("tree_bypass", "holder") is True
    result = asyncio.run(controller.run_search("tree_bypass", acquire_lease=False))
    assert result.champion is not None


def test_lease_contention_raises_before_any_event(tmp_path: Path) -> None:
    controller = _make_controller(
        tmp_path, SearchPolicy(max_iterations=1, branching_factor=1, max_depth=2, require_lease=True)
    )
    assert controller.store.acquire_lease("tree_busy", "holder") is True

    with pytest.raises(LeaseAcquisitionError):
        asyncio.run(controller.run_search("tree_busy"))

    assert controller.store.get_events("tree_busy") == []
