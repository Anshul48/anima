"""Shared pytest fixtures for SST unit and integration test suites."""

from __future__ import annotations

from pathlib import Path

import pytest

from sst.gateway.contracts import (
    ModelCatalog,
    ModelCatalogEntry,
    ProviderKind,
    ProviderProfile,
)
from sst.gateway.gateway import ModelGateway
from sst.storage.store import SQLiteSSTStore


@pytest.fixture
def temp_workspace(tmp_path: Path) -> Path:
    """Provides an isolated workspace directory."""
    ws = tmp_path / "workspace"
    ws.mkdir(parents=True, exist_ok=True)
    return ws


@pytest.fixture
def temp_store(tmp_path: Path) -> SQLiteSSTStore:
    """Provides a fresh temporary SQLiteSSTStore."""
    db_path = tmp_path / "test_store.db"
    return SQLiteSSTStore(db_path)


@pytest.fixture
def fake_gateway() -> ModelGateway:
    """Provides a preconfigured deterministic ModelGateway."""
    gw = ModelGateway()
    prof = ProviderProfile(
        name="test-profile",
        kind=ProviderKind.TEST,
        api_base="test://",
        catalog=ModelCatalog(models=[ModelCatalogEntry(id="fake-model", display_label="Fake Model")]),
    )
    gw.register_profile(prof)
    gw.set_route("diverge", "test-profile", "fake-model")
    gw.set_route("refine", "test-profile", "fake-model")
    gw.set_route("critique", "test-profile", "fake-model")
    gw.set_route("synthesize", "test-profile", "fake-model")
    return gw
