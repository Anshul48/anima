"""Module: stc.memory.trace_client
Local Project Trace SQLite FTS5 database client for episodic memory.
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from stc.core.config import get_settings
from stc.core.errors import TraceMemoryError
from stc.protocols.interfaces import TraceMemoryProtocol


class TraceClient(TraceMemoryProtocol):
    """Client for querying Project Trace SQLite FTS5 episodic memory store."""

    def __init__(self, db_path: Path | str | None = None, timeout: float = 5.0) -> None:
        if db_path is not None:
            self.db_path = Path(db_path)
        else:
            self.db_path = get_settings().trace_db_path
        self.timeout = timeout

    @property
    def has_live_db(self) -> bool:
        """Check if the physical Trace database exists on disk."""
        return self.db_path.is_file()

    def init_schema(self) -> None:
        """Initialize the Project Trace SQLite tables if they do not exist."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.db_path), timeout=self.timeout)
        try:
            with conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS documents (
                        document_id TEXT PRIMARY KEY,
                        document_name TEXT NOT NULL,
                        collection TEXT DEFAULT 'default'
                    );
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS atoms (
                        atom_id TEXT PRIMARY KEY,
                        document_id TEXT NOT NULL REFERENCES documents(document_id),
                        content TEXT NOT NULL
                    );
                    """
                )
                conn.execute(
                    """
                    CREATE VIRTUAL TABLE IF NOT EXISTS lexical_fts USING fts5(
                        atom_id UNINDEXED,
                        content,
                        tokenize='porter'
                    );
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS proposals (
                        proposal_id TEXT PRIMARY KEY,
                        status TEXT NOT NULL,
                        proposal_type TEXT NOT NULL,
                        candidate_json TEXT DEFAULT '{}',
                        decision_reason TEXT NOT NULL,
                        component TEXT DEFAULT '',
                        created_event_id INTEGER DEFAULT 1
                    );
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS events (
                        event_id TEXT PRIMARY KEY,
                        event_type TEXT NOT NULL,
                        payload_hash TEXT DEFAULT '',
                        created_at TEXT DEFAULT CURRENT_TIMESTAMP
                    );
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS attachments (
                        attachment_id TEXT PRIMARY KEY,
                        document_id TEXT,
                        payload BLOB
                    );
                    """
                )
        except sqlite3.Error as exc:
            raise TraceMemoryError(f"Failed to initialize Trace DB schema: {exc}") from exc
        finally:
            conn.close()

    def insert_document(
        self, document_id: str, document_name: str, collection: str = "default"
    ) -> None:
        """Insert a document record."""
        if not self.has_live_db:
            self.init_schema()
        conn = sqlite3.connect(str(self.db_path), timeout=self.timeout)
        try:
            with conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO documents (document_id, document_name, collection)
                    VALUES (?, ?, ?);
                    """,
                    (document_id, document_name, collection),
                )
        except sqlite3.Error as exc:
            raise TraceMemoryError(f"Failed to insert document: {exc}") from exc
        finally:
            conn.close()

    def insert_atom(self, atom_id: str, document_id: str, content: str) -> None:
        """Insert an atom and index its content into lexical_fts."""
        if not self.has_live_db:
            self.init_schema()
        conn = sqlite3.connect(str(self.db_path), timeout=self.timeout)
        try:
            with conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO atoms (atom_id, document_id, content)
                    VALUES (?, ?, ?);
                    """,
                    (atom_id, document_id, content),
                )
                conn.execute(
                    "INSERT INTO lexical_fts (atom_id, content) VALUES (?, ?);",
                    (atom_id, content),
                )
        except sqlite3.Error as exc:
            raise TraceMemoryError(f"Failed to insert atom: {exc}") from exc
        finally:
            conn.close()

    def insert_proposal(
        self,
        proposal_id: str,
        status: str,
        proposal_type: str,
        decision_reason: str,
        candidate_json: str = "{}",
        component: str = "",
        created_event_id: int = 1,
    ) -> None:
        """Insert a proposal record (such as a negative inhibitor)."""
        if not self.has_live_db:
            self.init_schema()
        conn = sqlite3.connect(str(self.db_path), timeout=self.timeout)
        try:
            with conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO proposals
                    (proposal_id, status, proposal_type, candidate_json,
                     decision_reason, component, created_event_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        proposal_id,
                        status,
                        proposal_type,
                        candidate_json,
                        decision_reason,
                        component,
                        created_event_id,
                    ),
                )
        except sqlite3.Error as exc:
            raise TraceMemoryError(f"Failed to insert proposal: {exc}") from exc
        finally:
            conn.close()

    def query_semantic_context(self, keywords: list[str], max_results: int = 3) -> list[str]:
        """Query lexical_fts for semantic context atoms matching keywords."""
        if not self.has_live_db or not keywords:
            return []

        clean_tokens = [re.sub(r"[^\w\-]", "", kw).strip() for kw in keywords]
        clean_tokens = [t.strip("-") for t in clean_tokens if t.strip("-")]
        if not clean_tokens:
            return []

        query_expr = " OR ".join(f'"{t}"' for t in clean_tokens)
        conn = sqlite3.connect(str(self.db_path), timeout=self.timeout)
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT
                    a.atom_id,
                    d.document_name,
                    snippet(lexical_fts, 1, '<b>', '</b>', '...', 10) AS match_snippet
                FROM lexical_fts
                JOIN atoms a ON a.atom_id = lexical_fts.atom_id
                JOIN documents d ON d.document_id = a.document_id
                WHERE lexical_fts MATCH :query
                ORDER BY rank LIMIT :limit;
                """,
                {"query": query_expr, "limit": max(1, max_results)},
            )
            rows = cursor.fetchall()
            results: list[str] = []
            for row in rows:
                atom_id = row[0] or ""
                doc_name = row[1] or ""
                snippet = row[2] or ""
                results.append(f"[{doc_name}:{atom_id}] {snippet}")
            return results
        except sqlite3.Error as exc:
            msg = f"Failed to query semantic context from Trace DB: {exc}"
            raise TraceMemoryError(msg) from exc
        finally:
            conn.close()

    def query_negative_inhibitors(self, component: str) -> list[str]:
        """Query proposals for historical failure patterns and negative inhibitors."""
        if not self.has_live_db:
            return []

        conn = sqlite3.connect(str(self.db_path), timeout=self.timeout)
        try:
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(proposals);")
            cols = {row[1] for row in cursor.fetchall()}
            has_comp = "component" in cols

            if has_comp:
                cursor.execute(
                    """
                    SELECT proposal_id, candidate_json, decision_reason, component
                    FROM proposals
                    WHERE status IN ('REJECTED', 'REFUTED', 'QUARANTINED')
                      AND proposal_type = 'negative_inhibitor'
                    ORDER BY created_event_id DESC;
                    """
                )
            else:
                cursor.execute(
                    """
                    SELECT proposal_id, candidate_json, decision_reason, ''
                    FROM proposals
                    WHERE status IN ('REJECTED', 'REFUTED', 'QUARANTINED')
                      AND proposal_type = 'negative_inhibitor'
                    ORDER BY created_event_id DESC;
                    """
                )
            rows = cursor.fetchall()
            matched: list[str] = []
            target_comp = component.strip().lower()

            for row in rows:
                _prop_id = row[0]
                cand_json = (row[1] or "").lower()
                reason = (row[2] or "").strip()
                row_comp = (row[3] or "").strip().lower()

                if not reason:
                    continue

                if (
                    not target_comp
                    or target_comp == "*"
                    or (row_comp and row_comp == target_comp)
                    or (cand_json and target_comp in cand_json)
                    or (target_comp in reason.lower())
                ):
                    matched.append(reason)

                if len(matched) >= 5:
                    break
            return matched
        except sqlite3.Error as exc:
            msg = f"Failed to query negative inhibitors from Trace DB: {exc}"
            raise TraceMemoryError(msg) from exc
        finally:
            conn.close()


__all__ = ["TraceClient"]
