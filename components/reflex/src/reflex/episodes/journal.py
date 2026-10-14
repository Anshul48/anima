"""Reflex Local Episode Journal.

Append-only, content-addressable SQLite and JSONL ledger recording verified execution
transitions (S_t, A_t, S_{t+1}, ΔS, surprise) indexed by state hashes and episode IDs.
Enforces WAL mode, foreign key integrity, and transaction rollback safety.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
import threading
from typing import Any, Dict, List, Optional, Tuple

from reflex.episodes.redactor import PrivacyRedactor
from reflex.ports.memory import (
    MemoryConnectionError,
    MemoryLockError,
    MemoryPort,
    MemoryPortError,
    MemoryReadOnlyError,
)
from reflex.schemas.actions import ActionType, NormalizedCoords, SafetyClass, TypedAction
from reflex.schemas.delta import OutcomeClass, StateDelta
from reflex.schemas.memory import MotorSkill, TransitionTuple


@dataclass(frozen=True)
class EpisodeSummary:
    """High-level summary of an execution episode."""

    episode_id: str
    task_goal: str
    total_steps: int
    success: bool
    duration_ms: float
    transition_ids: List[str]
    session_id: str = ""
    start_time_ms: float = 0.0
    end_time_ms: Optional[float] = None
    final_outcome: str = "success"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "episode_id": self.episode_id,
            "task_goal": self.task_goal,
            "total_steps": self.total_steps,
            "success": self.success,
            "duration_ms": self.duration_ms,
            "transition_ids": list(self.transition_ids),
            "session_id": self.session_id,
            "start_time_ms": self.start_time_ms,
            "end_time_ms": self.end_time_ms,
            "final_outcome": self.final_outcome,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> EpisodeSummary:
        return cls(
            episode_id=data["episode_id"],
            task_goal=data.get("task_goal", ""),
            total_steps=int(data.get("total_steps", 0)),
            success=bool(data.get("success", False)),
            duration_ms=float(data.get("duration_ms", 0.0)),
            transition_ids=list(data.get("transition_ids", [])),
            session_id=data.get("session_id", ""),
            start_time_ms=float(data.get("start_time_ms", 0.0)),
            end_time_ms=float(data["end_time_ms"]) if data.get("end_time_ms") is not None else None,
            final_outcome=data.get("final_outcome", "success"),
            metadata=data.get("metadata", {}),
        )


class EpisodeJournalPort(MemoryPort, ABC):
    """Abstract port for persisting episodes, transition tuples, and querying execution ledgers."""

    @abstractmethod
    async def record_transition(self, transition: TransitionTuple) -> None:
        """Persists a verified transition tuple to the local journal."""
        ...

    @abstractmethod
    async def get_episode_transitions(self, episode_id: str) -> List[TransitionTuple]:
        """Retrieves all chronological transitions for a given episode."""
        ...

    @abstractmethod
    async def find_transitions_by_state(self, state_hash: str) -> List[TransitionTuple]:
        """Retrieves historical transitions originating from a specific UI state hash."""
        ...

    async def start_episode(
        self,
        episode_id: str,
        session_id: str,
        task_goal: str,
        start_time_ms: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Initializes a new episode ledger record."""
        pass

    async def end_episode(
        self,
        episode_id: str,
        final_outcome: str = "success",
        end_time_ms: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Finalizes an episode record with final outcome and timestamp."""
        pass

    async def get_episode_summary(self, episode_id: str) -> Optional[EpisodeSummary]:
        """Retrieves a consolidated EpisodeSummary for the given episode."""
        return None

    async def list_episodes(self) -> List[EpisodeSummary]:
        """Lists summaries of all registered episodes."""
        return []


class LocalEpisodeJournal(EpisodeJournalPort):
    """Local SQLite & JSONL implementation of EpisodeJournalPort.

    Features:
    - Write-Ahead Logging (WAL) mode for fast non-blocking concurrent reads
    - Transaction rollback safety on failure
    - Client-side privacy redaction before persistence
    - Cryptographic state hash indexing (ui_state_hash -> next_ui_state_hash)
    - Full MotorSkill caching and querying
    - Optional JSONL streaming ledger sync
    """

    def __init__(
        self,
        db_path: str = ":memory:",
        jsonl_path: Optional[str] = None,
        redactor: Optional[PrivacyRedactor] = None,
        auto_redact: bool = True,
    ) -> None:
        self.db_path = db_path
        self.jsonl_path = jsonl_path
        self.redactor = redactor or (PrivacyRedactor() if auto_redact else None)
        self._lock = threading.RLock()
        self._db_conn: Optional[sqlite3.Connection] = None
        self._init_db()

    def _init_db(self) -> None:
        """Initializes SQLite database connection, PRAGMAs, tables, and indexes."""
        if self.db_path != ":memory:":
            parent_dir = Path(self.db_path).parent
            parent_dir.mkdir(parents=True, exist_ok=True)

        self._db_conn = sqlite3.connect(
            self.db_path,
            check_same_thread=False,
            timeout=10.0,
        )
        self._db_conn.row_factory = sqlite3.Row

        with self._lock:
            cur = self._db_conn.cursor()

            # Set WAL mode and connection tuning
            try:
                cur.execute("PRAGMA journal_mode=WAL;")
                cur.execute("PRAGMA synchronous=NORMAL;")
                cur.execute("PRAGMA foreign_keys=ON;")
                cur.execute("PRAGMA busy_timeout=5000;")
            except sqlite3.OperationalError:
                pass

            # Episodes table
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS episodes (
                    episode_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    task_goal TEXT NOT NULL,
                    start_time_ms REAL NOT NULL,
                    end_time_ms REAL,
                    total_steps INTEGER NOT NULL DEFAULT 0,
                    final_outcome TEXT NOT NULL DEFAULT 'in_progress',
                    metadata_json TEXT
                );
                """
            )

            # Transitions table
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS transitions (
                    transition_id TEXT PRIMARY KEY,
                    episode_id TEXT NOT NULL,
                    step_index INTEGER NOT NULL,
                    timestamp_ms REAL NOT NULL,
                    ui_state_hash TEXT NOT NULL,
                    next_ui_state_hash TEXT,
                    action_json TEXT NOT NULL,
                    delta_json TEXT NOT NULL,
                    surprise_score REAL NOT NULL,
                    duration_ms REAL NOT NULL,
                    provenance_json TEXT,
                    goal_text TEXT NOT NULL DEFAULT '',
                    goal_embedding TEXT NOT NULL DEFAULT '[]',
                    visual_embedding TEXT,
                    FOREIGN KEY(episode_id) REFERENCES episodes(episode_id) ON DELETE CASCADE
                );
                """
            )

            # Skills table
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS skills (
                    skill_id TEXT PRIMARY KEY,
                    version INTEGER NOT NULL,
                    preconditions_hash TEXT NOT NULL,
                    goal_embedding TEXT NOT NULL,
                    visual_context_embedding TEXT NOT NULL,
                    action_sequence_json TEXT NOT NULL,
                    expected_delta_json TEXT NOT NULL,
                    timing_mean_ms REAL NOT NULL,
                    timing_std_ms REAL NOT NULL,
                    confidence REAL NOT NULL,
                    safety_class TEXT NOT NULL,
                    provenance_episode_ids_json TEXT NOT NULL,
                    validated_count INTEGER NOT NULL,
                    last_validated TEXT NOT NULL
                );
                """
            )

            # Indexes
            cur.execute("CREATE INDEX IF NOT EXISTS idx_transitions_state_hash ON transitions(ui_state_hash);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_transitions_next_hash ON transitions(next_ui_state_hash);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_transitions_episode ON transitions(episode_id, step_index);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_skills_pre ON skills(preconditions_hash);")

            self._db_conn.commit()

    def _ensure_connected(self) -> sqlite3.Connection:
        if self._db_conn is None:
            raise MemoryConnectionError("Episode journal SQLite database is closed or disconnected")
        return self._db_conn

    def _handle_sqlite_error(self, err: Exception, message: str = "Database operation failed") -> None:
        if isinstance(err, (MemoryConnectionError, MemoryLockError, MemoryReadOnlyError)):
            raise err

        err_msg = str(err).lower()
        if "locked" in err_msg or "busy" in err_msg:
            raise MemoryLockError(f"{message}: lock contention ({err})") from err
        if "readonly" in err_msg or "read-only" in err_msg:
            raise MemoryReadOnlyError(f"{message}: read only database ({err})") from err
        raise MemoryPortError(f"{message}: {err}") from err

    async def start_episode(
        self,
        episode_id: str,
        session_id: str,
        task_goal: str,
        start_time_ms: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Initializes a new episode record in the ledger."""
        conn = self._ensure_connected()
        t_start = start_time_ms if start_time_ms is not None else datetime.now(timezone.utc).timestamp() * 1000.0
        meta_json = json.dumps(metadata or {})

        with self._lock:
            try:
                cur = conn.cursor()
                cur.execute(
                    """
                    INSERT INTO episodes (
                        episode_id, session_id, task_goal, start_time_ms, end_time_ms, total_steps, final_outcome, metadata_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(episode_id) DO UPDATE SET
                        session_id=excluded.session_id,
                        task_goal=excluded.task_goal,
                        start_time_ms=excluded.start_time_ms,
                        metadata_json=excluded.metadata_json
                    """,
                    (episode_id, session_id, task_goal, t_start, None, 0, "in_progress", meta_json),
                )
                conn.commit()
            except Exception as e:
                conn.rollback()
                self._handle_sqlite_error(e, f"Failed to start episode {episode_id}")

    async def end_episode(
        self,
        episode_id: str,
        final_outcome: str = "success",
        end_time_ms: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Finalizes an episode record with final outcome and timestamp."""
        conn = self._ensure_connected()
        t_end = end_time_ms if end_time_ms is not None else datetime.now(timezone.utc).timestamp() * 1000.0

        with self._lock:
            try:
                cur = conn.cursor()
                # Count current transitions
                cur.execute("SELECT COUNT(*) FROM transitions WHERE episode_id = ?", (episode_id,))
                count_row = cur.fetchone()
                total_steps = count_row[0] if count_row else 0

                cur.execute("SELECT metadata_json FROM episodes WHERE episode_id = ?", (episode_id,))
                existing_row = cur.fetchone()
                if existing_row and existing_row["metadata_json"]:
                    try:
                        merged_meta = json.loads(existing_row["metadata_json"])
                    except Exception:
                        merged_meta = {}
                else:
                    merged_meta = {}

                if metadata:
                    merged_meta.update(metadata)

                cur.execute(
                    """
                    UPDATE episodes
                    SET end_time_ms = ?,
                        final_outcome = ?,
                        total_steps = ?,
                        metadata_json = ?
                    WHERE episode_id = ?
                    """,
                    (t_end, final_outcome, total_steps, json.dumps(merged_meta), episode_id),
                )
                conn.commit()
            except Exception as e:
                conn.rollback()
                self._handle_sqlite_error(e, f"Failed to end episode {episode_id}")

    async def record_transition(
        self,
        transition: TransitionTuple,
        scrub: Optional[bool] = None,
    ) -> None:
        """Persists a verified transition tuple to the local journal."""
        conn = self._ensure_connected()

        # Apply redaction if redactor is active and scrubbing requested
        should_scrub = scrub if scrub is not None else (self.redactor is not None)
        if should_scrub and self.redactor is not None:
            tx = self.redactor.redact_transition(transition)
        else:
            tx = transition

        with self._lock:
            try:
                cur = conn.cursor()

                # Ensure parent episode exists to satisfy foreign key constraints
                cur.execute(
                    """
                    INSERT INTO episodes (
                        episode_id, session_id, task_goal, start_time_ms, end_time_ms, total_steps, final_outcome, metadata_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(episode_id) DO NOTHING
                    """,
                    (tx.episode_id, tx.episode_id, tx.goal_text, tx.timestamp_ms, None, 0, "in_progress", "{}"),
                )

                # Insert or replace transition
                cur.execute(
                    """
                    INSERT INTO transitions (
                        transition_id, episode_id, step_index, timestamp_ms,
                        ui_state_hash, next_ui_state_hash, action_json, delta_json,
                        surprise_score, duration_ms, provenance_json,
                        goal_text, goal_embedding, visual_embedding
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(transition_id) DO UPDATE SET
                        episode_id=excluded.episode_id,
                        step_index=excluded.step_index,
                        timestamp_ms=excluded.timestamp_ms,
                        ui_state_hash=excluded.ui_state_hash,
                        next_ui_state_hash=excluded.next_ui_state_hash,
                        action_json=excluded.action_json,
                        delta_json=excluded.delta_json,
                        surprise_score=excluded.surprise_score,
                        duration_ms=excluded.duration_ms,
                        provenance_json=excluded.provenance_json,
                        goal_text=excluded.goal_text,
                        goal_embedding=excluded.goal_embedding,
                        visual_embedding=excluded.visual_embedding
                    """,
                    (
                        tx.transition_id,
                        tx.episode_id,
                        tx.step_index,
                        tx.timestamp_ms,
                        tx.ui_state_hash,
                        tx.next_ui_state_hash,
                        json.dumps(tx.action.to_dict()),
                        json.dumps(tx.delta.to_dict()),
                        tx.surprise_score,
                        tx.duration_ms,
                        json.dumps(tx.provenance),
                        tx.goal_text,
                        json.dumps(tx.goal_embedding),
                        json.dumps(tx.visual_embedding) if tx.visual_embedding is not None else None,
                    ),
                )

                # Update episode total_steps and end_time_ms
                cur.execute("SELECT COUNT(*) FROM transitions WHERE episode_id = ?", (tx.episode_id,))
                cnt_row = cur.fetchone()
                total_steps = cnt_row[0] if cnt_row else 1
                cur.execute(
                    "UPDATE episodes SET total_steps = ?, end_time_ms = ? WHERE episode_id = ?",
                    (total_steps, tx.timestamp_ms + tx.duration_ms, tx.episode_id),
                )

                conn.commit()
            except Exception as e:
                conn.rollback()
                self._handle_sqlite_error(e, f"Failed to record transition {transition.transition_id}")

        # Optional JSONL streaming ledger append
        if self.jsonl_path:
            self._append_to_jsonl(tx)

    def _append_to_jsonl(self, transition: TransitionTuple) -> None:
        """Appends a transition dictionary line to the configured JSONL file."""
        try:
            p = Path(self.jsonl_path)
            p.parent.mkdir(parents=True, exist_ok=True)
            with open(p, "a", encoding="utf-8") as f:
                f.write(json.dumps(transition.to_dict()) + "\n")
        except Exception:
            pass

    async def get_episode_transitions(self, episode_id: str) -> List[TransitionTuple]:
        """Retrieves all chronological transitions for a given episode."""
        conn = self._ensure_connected()
        with self._lock:
            try:
                cur = conn.cursor()
                cur.execute(
                    """
                    SELECT * FROM transitions
                    WHERE episode_id = ?
                    ORDER BY step_index ASC, timestamp_ms ASC
                    """,
                    (episode_id,),
                )
                rows = cur.fetchall()
                return [self._row_to_transition(r) for r in rows]
            except Exception as e:
                self._handle_sqlite_error(e, f"Failed to fetch transitions for episode {episode_id}")
                return []

    async def find_transitions_by_state(self, state_hash: str) -> List[TransitionTuple]:
        """Retrieves historical transitions originating from a specific UI state hash."""
        conn = self._ensure_connected()
        with self._lock:
            try:
                cur = conn.cursor()
                cur.execute(
                    """
                    SELECT * FROM transitions
                    WHERE ui_state_hash = ?
                    ORDER BY timestamp_ms ASC
                    """,
                    (state_hash,),
                )
                rows = cur.fetchall()
                return [self._row_to_transition(r) for r in rows]
            except Exception as e:
                self._handle_sqlite_error(e, f"Failed to find transitions for state {state_hash}")
                return []

    async def get_episode_summary(self, episode_id: str) -> Optional[EpisodeSummary]:
        """Retrieves a consolidated EpisodeSummary for the given episode."""
        conn = self._ensure_connected()
        with self._lock:
            try:
                cur = conn.cursor()
                cur.execute("SELECT * FROM episodes WHERE episode_id = ?", (episode_id,))
                ep_row = cur.fetchone()
                if not ep_row:
                    return None

                cur.execute(
                    "SELECT transition_id, duration_ms FROM transitions WHERE episode_id = ? ORDER BY step_index ASC",
                    (episode_id,),
                )
                trans_rows = cur.fetchall()
                trans_ids = [r["transition_id"] for r in trans_rows]
                total_duration = sum(float(r["duration_ms"]) for r in trans_rows)

                start_time = float(ep_row["start_time_ms"])
                end_time = float(ep_row["end_time_ms"]) if ep_row["end_time_ms"] is not None else None
                if total_duration == 0.0 and end_time is not None:
                    total_duration = max(0.0, end_time - start_time)

                final_outcome = str(ep_row["final_outcome"])
                success = final_outcome.lower() in ("success", "completed", "done", "passed")

                try:
                    meta = json.loads(ep_row["metadata_json"]) if ep_row["metadata_json"] else {}
                except Exception:
                    meta = {}

                return EpisodeSummary(
                    episode_id=ep_row["episode_id"],
                    task_goal=ep_row["task_goal"],
                    total_steps=int(ep_row["total_steps"]),
                    success=success,
                    duration_ms=total_duration,
                    transition_ids=trans_ids,
                    session_id=ep_row["session_id"],
                    start_time_ms=start_time,
                    end_time_ms=end_time,
                    final_outcome=final_outcome,
                    metadata=meta,
                )
            except Exception as e:
                self._handle_sqlite_error(e, f"Failed to get summary for episode {episode_id}")
                return None

    async def list_episodes(self) -> List[EpisodeSummary]:
        """Lists summaries of all registered episodes."""
        conn = self._ensure_connected()
        with self._lock:
            try:
                cur = conn.cursor()
                cur.execute("SELECT episode_id FROM episodes ORDER BY start_time_ms ASC")
                rows = cur.fetchall()
                ep_ids = [r["episode_id"] for r in rows]
            except Exception as e:
                self._handle_sqlite_error(e, "Failed to list episodes")
                return []

        summaries: List[EpisodeSummary] = []
        for ep_id in ep_ids:
            summary = await self.get_episode_summary(ep_id)
            if summary:
                summaries.append(summary)
        return summaries

    async def verify_cryptographic_linkage(self, episode_id: str) -> Tuple[bool, Optional[str]]:
        """Verifies that transitions form an unbroken chain of state hashes (next_hash_t == hash_{t+1})."""
        transitions = await self.get_episode_transitions(episode_id)
        if not transitions or len(transitions) <= 1:
            return True, None

        for i in range(len(transitions) - 1):
            curr_tx = transitions[i]
            next_tx = transitions[i + 1]

            expected_next = curr_tx.next_ui_state_hash
            observed_origin = next_tx.ui_state_hash

            if expected_next is not None and expected_next != observed_origin:
                reason = (
                    f"Linkage break between step {curr_tx.step_index} and {next_tx.step_index}: "
                    f"step {curr_tx.step_index}.next_ui_state_hash='{expected_next}' != "
                    f"step {next_tx.step_index}.ui_state_hash='{observed_origin}'"
                )
                return False, reason

        return True, None

    # =========================================================================
    # Motor Skill Methods
    # =========================================================================

    async def save_skill(self, skill: MotorSkill) -> None:
        """Saves or updates a compiled MotorSkill in the SQLite ledger."""
        conn = self._ensure_connected()
        last_val = (
            skill.last_validated.isoformat()
            if isinstance(skill.last_validated, datetime)
            else str(skill.last_validated)
        )

        with self._lock:
            try:
                cur = conn.cursor()
                cur.execute(
                    """
                    INSERT INTO skills (
                        skill_id, version, preconditions_hash, goal_embedding,
                        visual_context_embedding, action_sequence_json,
                        expected_delta_json, timing_mean_ms, timing_std_ms,
                        confidence, safety_class, provenance_episode_ids_json,
                        validated_count, last_validated
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(skill_id) DO UPDATE SET
                        version=excluded.version,
                        preconditions_hash=excluded.preconditions_hash,
                        goal_embedding=excluded.goal_embedding,
                        visual_context_embedding=excluded.visual_context_embedding,
                        action_sequence_json=excluded.action_sequence_json,
                        expected_delta_json=excluded.expected_delta_json,
                        timing_mean_ms=excluded.timing_mean_ms,
                        timing_std_ms=excluded.timing_std_ms,
                        confidence=excluded.confidence,
                        safety_class=excluded.safety_class,
                        provenance_episode_ids_json=excluded.provenance_episode_ids_json,
                        validated_count=excluded.validated_count,
                        last_validated=excluded.last_validated
                    """,
                    (
                        skill.skill_id,
                        skill.version,
                        skill.preconditions_hash,
                        json.dumps(skill.goal_embedding),
                        json.dumps(skill.visual_context_embedding),
                        json.dumps([a.to_dict() for a in skill.action_sequence]),
                        json.dumps(skill.expected_delta.to_dict()),
                        skill.timing_mean_ms,
                        skill.timing_std_ms,
                        skill.confidence,
                        skill.safety_class.value if isinstance(skill.safety_class, SafetyClass) else str(skill.safety_class),
                        json.dumps(skill.provenance_episode_ids),
                        skill.validated_count,
                        last_val,
                    ),
                )
                conn.commit()
            except Exception as e:
                conn.rollback()
                self._handle_sqlite_error(e, f"Failed to save skill {skill.skill_id}")

    async def record_skill(self, skill: MotorSkill) -> None:
        """Alias for save_skill."""
        await self.save_skill(skill)

    async def get_skill(self, skill_id: str) -> Optional[MotorSkill]:
        """Retrieves a MotorSkill by ID."""
        conn = self._ensure_connected()
        with self._lock:
            try:
                cur = conn.cursor()
                cur.execute("SELECT * FROM skills WHERE skill_id = ?", (skill_id,))
                row = cur.fetchone()
                if not row:
                    return None
                return self._row_to_skill(row)
            except Exception as e:
                self._handle_sqlite_error(e, f"Failed to get skill {skill_id}")
                return None

    async def find_skills_by_preconditions(self, preconditions_hash: str) -> List[MotorSkill]:
        """Retrieves motor skills matching preconditions hash."""
        conn = self._ensure_connected()
        with self._lock:
            try:
                cur = conn.cursor()
                cur.execute(
                    "SELECT * FROM skills WHERE preconditions_hash = ? ORDER BY confidence DESC",
                    (preconditions_hash,),
                )
                rows = cur.fetchall()
                return [self._row_to_skill(r) for r in rows]
            except Exception as e:
                self._handle_sqlite_error(e, f"Failed to find skills for hash {preconditions_hash}")
                return []

    async def list_skills(self) -> List[MotorSkill]:
        """Lists all motor skills in the ledger."""
        conn = self._ensure_connected()
        with self._lock:
            try:
                cur = conn.cursor()
                cur.execute("SELECT * FROM skills ORDER BY skill_id ASC")
                rows = cur.fetchall()
                return [self._row_to_skill(r) for r in rows]
            except Exception as e:
                self._handle_sqlite_error(e, "Failed to list skills")
                return []

    # =========================================================================
    # JSONL Export and Import
    # =========================================================================

    async def export_to_jsonl(self, file_path: str, episode_id: Optional[str] = None) -> int:
        """Exports stored transitions to a JSONL file. Returns number of transitions written."""
        conn = self._ensure_connected()
        with self._lock:
            cur = conn.cursor()
            if episode_id:
                cur.execute(
                    "SELECT * FROM transitions WHERE episode_id = ? ORDER BY step_index ASC, timestamp_ms ASC",
                    (episode_id,),
                )
            else:
                cur.execute("SELECT * FROM transitions ORDER BY episode_id, step_index ASC, timestamp_ms ASC")
            rows = cur.fetchall()

        transitions = [self._row_to_transition(r) for r in rows]
        p = Path(file_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            for tx in transitions:
                f.write(json.dumps(tx.to_dict()) + "\n")
        return len(transitions)

    async def import_from_jsonl(self, file_path: str) -> int:
        """Imports transitions from a JSONL file into the journal. Returns count of transitions imported."""
        p = Path(file_path)
        if not p.exists():
            raise FileNotFoundError(f"JSONL file not found: {file_path}")

        count = 0
        with open(p, "r", encoding="utf-8") as f:
            for line in f:
                line_str = line.strip()
                if not line_str:
                    continue
                data = json.loads(line_str)
                tx = TransitionTuple.from_dict(data)
                await self.record_transition(tx, scrub=False)
                count += 1
        return count

    async def close(self) -> None:
        """Closes SQLite database connection cleanly."""
        with self._lock:
            if self._db_conn is not None:
                try:
                    self._db_conn.close()
                except Exception:
                    pass
                self._db_conn = None

    # =========================================================================
    # Deserialization Helpers
    # =========================================================================

    def _row_to_transition(self, row: sqlite3.Row) -> TransitionTuple:
        """Converts an SQLite row to a TransitionTuple."""
        goal_emb = json.loads(row["goal_embedding"]) if row["goal_embedding"] else []
        vis_emb = json.loads(row["visual_embedding"]) if row["visual_embedding"] is not None else None
        prov = json.loads(row["provenance_json"]) if row["provenance_json"] else {}
        action_data = json.loads(row["action_json"])
        delta_data = json.loads(row["delta_json"])

        return TransitionTuple(
            transition_id=row["transition_id"],
            episode_id=row["episode_id"],
            step_index=int(row["step_index"]),
            timestamp_ms=float(row["timestamp_ms"]),
            ui_state_hash=row["ui_state_hash"],
            goal_text=row["goal_text"],
            goal_embedding=[float(x) for x in goal_emb],
            visual_embedding=[float(x) for x in vis_emb] if vis_emb is not None else None,
            action=TypedAction.from_dict(action_data),
            next_ui_state_hash=row["next_ui_state_hash"],
            delta=StateDelta.from_dict(delta_data),
            duration_ms=float(row["duration_ms"]),
            surprise_score=float(row["surprise_score"]),
            provenance=prov,
        )

    def _row_to_skill(self, row: sqlite3.Row) -> MotorSkill:
        """Converts an SQLite row to a MotorSkill."""
        raw_actions = json.loads(row["action_sequence_json"])
        action_seq = [TypedAction.from_dict(a) for a in raw_actions]
        last_val_str = row["last_validated"]
        try:
            last_val = datetime.fromisoformat(last_val_str)
        except Exception:
            last_val = datetime.now(timezone.utc).replace(tzinfo=None)

        return MotorSkill(
            skill_id=row["skill_id"],
            version=int(row["version"]),
            preconditions_hash=row["preconditions_hash"],
            goal_embedding=json.loads(row["goal_embedding"]),
            visual_context_embedding=json.loads(row["visual_context_embedding"]),
            action_sequence=action_seq,
            expected_delta=StateDelta.from_dict(json.loads(row["expected_delta_json"])),
            timing_mean_ms=float(row["timing_mean_ms"]),
            timing_std_ms=float(row["timing_std_ms"]),
            confidence=float(row["confidence"]),
            safety_class=SafetyClass(row["safety_class"]),
            provenance_episode_ids=json.loads(row["provenance_episode_ids_json"]),
            validated_count=int(row["validated_count"]),
            last_validated=last_val,
        )
