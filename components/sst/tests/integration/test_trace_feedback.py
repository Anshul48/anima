"""Integration test verifying the bidirectional Project Trace membrane and negative inhibitor feedback loop."""

from __future__ import annotations

import asyncio
import json
import sqlite3
from pathlib import Path

from sst.context.capsule import ContextCapsuleCompiler
from sst.core.contracts import TaskPacket
from sst.core.events import EventKind
from sst.core.models import DomainMode
from sst.gateway.contracts import (
    GatewayRequest,
    GatewayResponse,
    ModelCatalog,
    ModelCatalogEntry,
    ProviderKind,
    ProviderProfile,
)
from sst.gateway.gateway import ModelGateway
from sst.prompts.dialectic import render_diverge_prompt
from sst.sandbox.custody import CandidateCustodyManager
from sst.search.controller import SSTSearchController
from sst.search.policy import SearchPolicy
from sst.storage.store import SQLiteSSTStore


class MockTraceDatabase:
    """Mock Project Trace SQLite substrate providing negative inhibitors and receiving refutations."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS negative_inhibitors (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    topic TEXT NOT NULL,
                    rule TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS trace_proposals (
                    proposal_id TEXT PRIMARY KEY,
                    tree_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    status TEXT NOT NULL,
                    refutation_reason TEXT
                )
                """
            )
            # Seed known negative inhibitor from prior build failure
            conn.execute(
                "INSERT INTO negative_inhibitors (topic, rule) VALUES (?, ?)",
                ("caching", "Never use unbounded in-memory dict without LRU eviction bounds"),
            )

    def query_negative_inhibitors(self, query: str) -> list[str]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute("SELECT rule FROM negative_inhibitors").fetchall()
            return [r[0] for r in rows]

    def record_refutation(self, proposal_id: str, tree_id: str, title: str, reason: str) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO trace_proposals (proposal_id, tree_id, title, status, refutation_reason)
                VALUES (?, ?, ?, 'REFUTED', ?)
                ON CONFLICT(proposal_id) DO UPDATE SET refutation_reason = excluded.refutation_reason
                """,
                (proposal_id, tree_id, title, reason),
            )

    def get_refutations(self, tree_id: str) -> list[tuple[str, str, str]]:
        with sqlite3.connect(self.db_path) as conn:
            return conn.execute(
                "SELECT proposal_id, title, refutation_reason FROM trace_proposals WHERE tree_id = ?",
                (tree_id,),
            ).fetchall()


def test_trace_negative_inhibitor_context_ingestion(tmp_path: Path) -> None:
    """Verifies that ContextCapsuleCompiler queries Trace and injects negative inhibitors."""
    trace_db = MockTraceDatabase(tmp_path / "trace.db")

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "cache.py").write_text("class Cache: pass\n")

    compiler = ContextCapsuleCompiler(workspace_root=workspace, trace_lite_db=trace_db)
    capsule = compiler.compile(
        goal="Design high performance cache",
        target_files=["cache.py"],
    )

    # Ingestion check: Negative inhibitor retrieved
    assert any("[NEGATIVE_INHIBITOR]" in s for s in capsule.literature_or_prior_insights)
    assert any("unbounded in-memory dict" in s for s in capsule.literature_or_prior_insights)

    # Prompt rendering check: Negative rules injected into DIVERGE prompt
    prompt = render_diverge_prompt(
        goal=capsule.goal,
        capsule=capsule,
        domain=DomainMode.AUTOBUILD,
        prior_attempts=[
            s.replace("[NEGATIVE_INHIBITOR] ", "")
            for s in capsule.literature_or_prior_insights
            if "[NEGATIVE_INHIBITOR]" in s
        ],
    )
    assert "LEARNED NEGATIVE RULES (AVOID REPEATING THESE)" in prompt
    assert "Never use unbounded in-memory dict without LRU eviction bounds" in prompt


def test_trace_bidirectional_feedback_loop(tmp_path: Path) -> None:
    """Verifies that pruned proposals feed refutations back to Trace and inform subsequent search."""
    trace_db = MockTraceDatabase(tmp_path / "trace.db")

    src_dir = tmp_path / "repo"
    src_dir.mkdir()
    (src_dir / "cache.py").write_text("class Cache:\n    def get(self, k): return None\n")
    (src_dir / "test_cache.py").write_text(
        "from cache import Cache\nc = Cache()\nassert hasattr(c, 'max_size'), 'Cache must enforce max_size invariant'\n"
    )

    task = TaskPacket(
        task_id="task_trace_test",
        goal="Implement bounded cache",
        source_repo_root=str(src_dir),
        base_commit="init_commit",
        snapshot_hash="hash_001",
        allowed_paths=["cache.py"],
        acceptance_commands=["python test_cache.py"],
    )

    store = SQLiteSSTStore(tmp_path / "sst_trace.db")
    custody = CandidateCustodyManager(base_worktree_dir=tmp_path / "worktrees")
    compiler = ContextCapsuleCompiler(workspace_root=src_dir, trace_lite_db=trace_db)

    # Gateway with failing proposal in iteration 0, succeeding in iteration 1
    call_count = 0

    class TraceAwareGateway(ModelGateway):
        def invoke(self, request: GatewayRequest) -> GatewayResponse:
            nonlocal call_count
            call_count += 1
            if request.role == "diverge":
                if call_count <= 1:
                    # Violates test (no max_size)
                    code = "class Cache:\n    def __init__(self): self.data = {}\n    def get(self, k): return self.data.get(k)\n"
                else:
                    # Compliant implementation
                    code = "class Cache:\n    def __init__(self, max_size=100): self.max_size = max_size; self.data = {}\n    def get(self, k): return self.data.get(k)\n"
                return GatewayResponse(
                    content=json.dumps(
                        {
                            "branches": [
                                {
                                    "strategy_title": "CacheCandidate",
                                    "hypothesis_or_rationale": "Testing",
                                    "proposed_changes": code,
                                }
                            ]
                        }
                    ),
                    profile="test-prof",
                    model="model-1",
                    total_tokens=50,
                )
            elif request.role == "critique":
                return GatewayResponse(
                    content=json.dumps({"value_score": 0.95, "verdict": "APPROVE", "critique": "Optimal"}),
                    profile="test-prof",
                    model="model-1",
                    total_tokens=30,
                )
            return GatewayResponse(content="{}", profile="test-prof", model="model-1", total_tokens=10)

    gw = TraceAwareGateway()
    gw.register_profile(
        ProviderProfile(
            name="test-prof",
            kind=ProviderKind.TEST,
            api_base="test://",
            catalog=ModelCatalog(models=[ModelCatalogEntry(id="model-1", display_label="Model 1")]),
        )
    )
    gw.set_route("diverge", "test-prof", "model-1")
    gw.set_route("refine", "test-prof", "model-1")
    gw.set_route("critique", "test-prof", "model-1")

    policy = SearchPolicy(max_iterations=2, branching_factor=1, max_depth=2)
    controller = SSTSearchController(
        task=task,
        gateway=gw,
        store=store,
        custody_manager=custody,
        policy=policy,
        capsule_compiler=compiler,
    )

    tree_id = "tree_trace_loop"
    champion = asyncio.run(controller.execute_search(tree_id))

    assert champion is not None
    assert "self.max_size" in champion.patch_diff

    # Verify that the failed candidate in iteration 0 emitted VERIFIER_FINISHED with passed=False
    events = store.get_events(tree_id)
    failed_ver_events = [
        e for e in events if e.kind == EventKind.VERIFIER_FINISHED and e.payload.get("passed") is False
    ]
    assert len(failed_ver_events) >= 1

    # Record refutations into Trace Database
    for f_evt in failed_ver_events:
        node_id = f_evt.node_id or "unknown"
        trace_db.record_refutation(
            proposal_id=node_id,
            tree_id=tree_id,
            title="Unbounded Cache Proposal",
            reason=f_evt.payload.get("stderr", "Verification failed"),
        )

    refutations = trace_db.get_refutations(tree_id)
    assert len(refutations) >= 1
    assert (
        "Verification failed" in refutations[0][2]
        or "AssertionError" in refutations[0][2]
        or "test_cache.py" in refutations[0][2]
    )
