"""SQLite persistent store for State Space Trees, append-only event sourcing, and node tracking."""

from __future__ import annotations

import contextlib
import json
import sqlite3
from collections.abc import Generator, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sst.core.events import EventKind, SSTEvent
from sst.core.models import (
    CortexEvaluation,
    DeterministicGateResult,
    DomainMode,
    NodeRole,
    NodeStatus,
    PayloadType,
    SSTNode,
    SSTTree,
)
from sst.storage.projection import DAGProjection


class SQLiteSSTStore:
    """Thread-safe, transaction-safe SQLite storage for append-only events, leases, and tree state."""

    def __init__(self, db_path: Path | str) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @contextlib.contextmanager
    def _connection(self) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(str(self.db_path), timeout=30.0)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self._connection() as conn:
            conn.executescript(
                """
                PRAGMA journal_mode=WAL;
                PRAGMA busy_timeout=5000;

                CREATE TABLE IF NOT EXISTS sst_trees (
                    tree_id TEXT PRIMARY KEY,
                    domain TEXT NOT NULL,
                    root_goal TEXT NOT NULL,
                    root_node_id TEXT NOT NULL,
                    active_frontier TEXT,
                    pruned_nodes TEXT,
                    winning_path TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS sst_nodes (
                    node_id TEXT PRIMARY KEY,
                    tree_id TEXT NOT NULL,
                    parent_id TEXT,
                    depth INTEGER NOT NULL,
                    domain TEXT NOT NULL,
                    role TEXT NOT NULL,
                    title TEXT NOT NULL,
                    status TEXT NOT NULL,
                    model TEXT,
                    temperature REAL,
                    payload_type TEXT NOT NULL,
                    content TEXT NOT NULL,
                    metadata_json TEXT,
                    visit_count INTEGER DEFAULT 0,
                    uct_score REAL DEFAULT 0.0,
                    value_score REAL DEFAULT 0.0,
                    deterministic_json TEXT,
                    cortex_json TEXT,
                    prune_reason TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (tree_id) REFERENCES sst_trees (tree_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS sst_events (
                    sequence_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT UNIQUE NOT NULL,
                    tree_id TEXT NOT NULL,
                    node_id TEXT,
                    kind TEXT NOT NULL,
                    event_version INTEGER DEFAULT 1,
                    actor TEXT DEFAULT 'controller',
                    policy_version TEXT DEFAULT 'v1',
                    idempotency_key TEXT UNIQUE NOT NULL,
                    payload_json TEXT NOT NULL,
                    artifact_hashes_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS sst_leases (
                    tree_id TEXT PRIMARY KEY,
                    owner TEXT NOT NULL,
                    expires_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_sst_nodes_tree_id ON sst_nodes (tree_id);
                CREATE INDEX IF NOT EXISTS idx_sst_nodes_parent_id ON sst_nodes (parent_id);
                CREATE INDEX IF NOT EXISTS idx_sst_nodes_status ON sst_nodes (status);
                CREATE INDEX IF NOT EXISTS idx_sst_events_tree_id ON sst_events (tree_id);
                CREATE INDEX IF NOT EXISTS idx_sst_events_seq ON sst_events (sequence_id);
                """
            )

    # --- Event Sourcing Methods ---

    def append_event(self, event: SSTEvent) -> int:
        """Appends an event to the append-only event log. Idempotently returns sequence_id on duplicate."""
        with self._connection() as conn:
            existing = conn.execute(
                "SELECT sequence_id FROM sst_events WHERE idempotency_key = ?",
                (event.idempotency_key,),
            ).fetchone()
            if existing:
                return int(existing["sequence_id"])

            cursor = conn.execute(
                """
                INSERT INTO sst_events (
                    event_id, tree_id, node_id, kind, event_version,
                    actor, policy_version, idempotency_key, payload_json,
                    artifact_hashes_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.event_id,
                    event.tree_id,
                    event.node_id,
                    event.kind.value,
                    event.event_version,
                    event.actor,
                    event.policy_version,
                    event.idempotency_key,
                    json.dumps(event.payload),
                    json.dumps(event.artifact_hashes),
                    event.created_at.isoformat(),
                ),
            )
            return int(cursor.lastrowid or 0)

    def get_events(self, tree_id: str, since_sequence: int = 0) -> list[SSTEvent]:
        """Retrieves chronological events for a given tree starting after since_sequence."""
        with self._connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM sst_events
                WHERE tree_id = ? AND sequence_id > ?
                ORDER BY sequence_id ASC
                """,
                (tree_id, since_sequence),
            ).fetchall()

            events: list[SSTEvent] = []
            for r in rows:
                events.append(
                    SSTEvent(
                        event_id=r["event_id"],
                        tree_id=r["tree_id"],
                        node_id=r["node_id"],
                        kind=EventKind(r["kind"]),
                        event_version=r["event_version"],
                        actor=r["actor"],
                        policy_version=r["policy_version"],
                        idempotency_key=r["idempotency_key"],
                        payload=json.loads(r["payload_json"] or "{}"),
                        artifact_hashes=json.loads(r["artifact_hashes_json"] or "{}"),
                        created_at=datetime.fromisoformat(r["created_at"]),
                    )
                )
            return events

    def rebuild_tree_from_events(self, tree_id: str) -> SSTTree | None:
        """Projects and returns the live SSTTree DAG by replaying all historical events."""
        events = self.get_events(tree_id=tree_id)
        if not events:
            return None
        return DAGProjection.replay_events(events=events, initial_tree_id=tree_id)

    # --- Lease Management Methods ---

    def acquire_lease(self, tree_id: str, owner: str, ttl_seconds: int = 60) -> bool:
        """Attempts to acquire or extend an exclusive writer lease on a tree."""
        now = datetime.now(UTC)
        expires = datetime.fromtimestamp(now.timestamp() + ttl_seconds, tz=UTC).isoformat()
        now_str = now.isoformat()

        with self._connection() as conn:
            row = conn.execute("SELECT owner, expires_at FROM sst_leases WHERE tree_id = ?", (tree_id,)).fetchone()
            if row:
                if row["owner"] != owner and row["expires_at"] > now_str:
                    return False
                conn.execute(
                    "UPDATE sst_leases SET owner = ?, expires_at = ? WHERE tree_id = ?",
                    (owner, expires, tree_id),
                )
            else:
                conn.execute(
                    "INSERT INTO sst_leases (tree_id, owner, expires_at) VALUES (?, ?, ?)",
                    (tree_id, owner, expires),
                )
            return True

    def release_lease(self, tree_id: str, owner: str) -> None:
        """Releases a writer lease if held by owner."""
        with self._connection() as conn:
            conn.execute("DELETE FROM sst_leases WHERE tree_id = ? AND owner = ?", (tree_id, owner))

    def report_outcome(
        self,
        *,
        tree_id: str,
        candidate_id: str,
        verdict: str,
        evidence_refs: Sequence[str] | None = None,
        actor: str,
        note: str | None = None,
        idempotency_key: str | None = None,
        event_id: str | None = None,
    ) -> int:
        """Records a domain outcome verdict verbatim as an OUTCOME_REPORTED event.

        Thin delegate of :func:`sst.sandbox.outcomes.report_outcome`: the
        verdict is stored verbatim under ``payload.domain_verdict`` with
        ``sst_authoritative: false`` and never satisfies promotion gates.
        Returns the appended event's sequence id.
        """
        from sst.sandbox.outcomes import report_outcome as _report_outcome

        return _report_outcome(
            self,
            tree_id=tree_id,
            candidate_id=candidate_id,
            verdict=verdict,
            evidence_refs=evidence_refs,
            actor=actor,
            note=note,
            idempotency_key=idempotency_key,
            event_id=event_id,
        )

    # --- Snapshot / Classic Tree Methods ---

    def save_tree(self, tree: SSTTree) -> None:
        """Persists or updates an SST tree and all its nodes."""
        with self._connection() as conn:
            conn.execute(
                """
                INSERT INTO sst_trees (tree_id, domain, root_goal, root_node_id, active_frontier, pruned_nodes, winning_path, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(tree_id) DO UPDATE SET
                    active_frontier = excluded.active_frontier,
                    pruned_nodes = excluded.pruned_nodes,
                    winning_path = excluded.winning_path
                """,
                (
                    tree.tree_id,
                    tree.domain.value,
                    tree.root_goal,
                    tree.root_node_id,
                    json.dumps(tree.active_frontier),
                    json.dumps(tree.pruned_nodes),
                    json.dumps(tree.winning_path),
                    tree.created_at.isoformat(),
                ),
            )

            for node in tree.nodes.values():
                self._save_node_tx(conn, node)

    def save_node(self, node: SSTNode) -> None:
        """Saves or updates a single SST node."""
        with self._connection() as conn:
            self._save_node_tx(conn, node)

    def _save_node_tx(self, conn: sqlite3.Connection, node: SSTNode) -> None:
        det_json = node.deterministic_result.model_dump_json() if node.deterministic_result else None
        cortex_json = node.cortex_evaluation.model_dump_json() if node.cortex_evaluation else None

        conn.execute(
            """
            INSERT INTO sst_nodes (
                node_id, tree_id, parent_id, depth, domain, role, title, status,
                model, temperature, payload_type, content, metadata_json,
                visit_count, uct_score, value_score, deterministic_json, cortex_json,
                prune_reason, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(node_id) DO UPDATE SET
                title = excluded.title,
                status = excluded.status,
                content = excluded.content,
                metadata_json = excluded.metadata_json,
                visit_count = excluded.visit_count,
                uct_score = excluded.uct_score,
                value_score = excluded.value_score,
                deterministic_json = excluded.deterministic_json,
                cortex_json = excluded.cortex_json,
                prune_reason = excluded.prune_reason,
                updated_at = excluded.updated_at
            """,
            (
                node.node_id,
                node.tree_id,
                node.parent_id,
                node.depth,
                node.domain.value,
                node.role.value,
                node.title,
                node.status.value,
                node.model,
                node.temperature,
                node.payload_type.value,
                node.content,
                json.dumps(node.metadata),
                node.visit_count,
                node.uct_score,
                node.value_score,
                det_json,
                cortex_json,
                node.prune_reason,
                node.created_at.isoformat(),
                node.updated_at.isoformat(),
            ),
        )

    def load_tree(self, tree_id: str) -> SSTTree | None:
        """Loads an entire SST tree and its constituent nodes from the store."""
        with self._connection() as conn:
            tree_row = conn.execute("SELECT * FROM sst_trees WHERE tree_id = ?", (tree_id,)).fetchone()
            if not tree_row:
                return None

            node_rows = conn.execute("SELECT * FROM sst_nodes WHERE tree_id = ?", (tree_id,)).fetchall()
            nodes: dict[str, SSTNode] = {}

            for r in node_rows:
                det_dict = json.loads(r["deterministic_json"]) if r["deterministic_json"] else None
                cortex_dict = json.loads(r["cortex_json"]) if r["cortex_json"] else None
                det_res = DeterministicGateResult(**det_dict) if det_dict else None
                cortex_eval = CortexEvaluation(**cortex_dict) if cortex_dict else None

                node = SSTNode(
                    node_id=r["node_id"],
                    parent_id=r["parent_id"],
                    tree_id=r["tree_id"],
                    depth=r["depth"],
                    domain=DomainMode(r["domain"]),
                    role=NodeRole(r["role"]),
                    title=r["title"],
                    status=NodeStatus(r["status"]),
                    model=r["model"] or "",
                    temperature=r["temperature"] or 0.7,
                    payload_type=PayloadType(r["payload_type"]),
                    content=r["content"],
                    metadata=json.loads(r["metadata_json"] or "{}"),
                    visit_count=r["visit_count"],
                    uct_score=r["uct_score"],
                    deterministic_result=det_res,
                    cortex_evaluation=cortex_eval,
                    prune_reason=r["prune_reason"],
                    created_at=datetime.fromisoformat(r["created_at"]),
                    updated_at=datetime.fromisoformat(r["updated_at"]),
                )
                nodes[node.node_id] = node

            return SSTTree(
                tree_id=tree_row["tree_id"],
                domain=DomainMode(tree_row["domain"]),
                root_goal=tree_row["root_goal"],
                root_node_id=tree_row["root_node_id"],
                nodes=nodes,
                active_frontier=json.loads(tree_row["active_frontier"] or "[]"),
                pruned_nodes=json.loads(tree_row["pruned_nodes"] or "[]"),
                winning_path=json.loads(tree_row["winning_path"] or "[]"),
                created_at=datetime.fromisoformat(tree_row["created_at"]),
            )

    def list_trees(self) -> list[dict[str, Any]]:
        """Lists metadata for all stored SST trees."""
        with self._connection() as conn:
            rows = conn.execute(
                """
                SELECT t.tree_id, t.domain, t.root_goal, t.created_at,
                       COUNT(n.node_id) as node_count
                FROM sst_trees t
                LEFT JOIN sst_nodes n ON t.tree_id = n.tree_id
                GROUP BY t.tree_id
                ORDER BY t.created_at DESC
                """
            ).fetchall()
            return [dict(r) for r in rows]
