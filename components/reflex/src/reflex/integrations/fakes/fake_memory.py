from __future__ import annotations
import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import json
import sqlite3
from typing import Any, Dict, List, Optional, Tuple

from reflex.ports.memory import (
    MemoryConnectionError,
    MemoryLockError,
    MemoryOutageError,
    MemoryPort,
    MemoryReadOnlyError,
)
from reflex.schemas.actions import ActionType, NormalizedCoords, SafetyClass, TypedAction
from reflex.schemas.delta import OutcomeClass, StateDelta
from reflex.schemas.memory import MotorSkill, TransitionTuple


class MemoryFaultMode(str, Enum):
    NORMAL = "normal"
    READ_ONLY = "read_only"
    DISCONNECTED = "disconnected"
    OUTAGE = "outage"
    LOCKED = "locked"
    CRASH = "crash"


@dataclass
class FakeMemoryConfig:
    """Configuration for FakeMemoryPort fault modes and storage engine."""
    mode: MemoryFaultMode = MemoryFaultMode.NORMAL
    storage_backend: str = "memory"  # "memory" or "sqlite"
    sqlite_path: Optional[str] = None  # None / ":memory:" or file path
    latency_ms: float = 0.0
    max_transitions: Optional[int] = None
    error_message: Optional[str] = None


def serialize_action(action: TypedAction) -> Dict[str, Any]:
    """Serializes a TypedAction dataclass to a JSON-compatible dictionary."""
    return {
        "action_type": action.action_type.value if hasattr(action.action_type, "value") else str(action.action_type),
        "target_node_id": action.target_node_id,
        "target_label": action.target_label,
        "coords": {"x": action.coords.x, "y": action.coords.y} if action.coords is not None else None,
        "text_payload": action.text_payload,
        "key_code": action.key_code,
        "scroll_delta": list(action.scroll_delta) if action.scroll_delta is not None else None,
        "safety_class": action.safety_class.value if hasattr(action.safety_class, "value") else str(action.safety_class),
        "metadata": dict(action.metadata),
    }


def deserialize_action(data: Dict[str, Any]) -> TypedAction:
    """Deserializes a dictionary into a TypedAction dataclass."""
    coords = None
    if data.get("coords") is not None:
        coords = NormalizedCoords(x=float(data["coords"]["x"]), y=float(data["coords"]["y"]))

    scroll_delta = None
    if data.get("scroll_delta") is not None:
        scroll_delta = (float(data["scroll_delta"][0]), float(data["scroll_delta"][1]))

    return TypedAction(
        action_type=ActionType(data["action_type"]),
        target_node_id=data.get("target_node_id"),
        target_label=data.get("target_label"),
        coords=coords,
        text_payload=data.get("text_payload"),
        key_code=data.get("key_code"),
        scroll_delta=scroll_delta,
        safety_class=SafetyClass(data.get("safety_class", SafetyClass.REVERSIBLE.value)),
        metadata=dict(data.get("metadata", {})),
    )


def serialize_delta(delta: StateDelta) -> Dict[str, Any]:
    """Serializes a StateDelta dataclass to a JSON-compatible dictionary."""
    return {
        "added_nodes": list(delta.added_nodes),
        "removed_nodes": list(delta.removed_nodes),
        "modified_nodes": list(delta.modified_nodes),
        "pixel_change_ratio": float(delta.pixel_change_ratio),
        "changed_bounding_boxes": [list(box) for box in delta.changed_bounding_boxes],
        "outcome_class": delta.outcome_class.value if hasattr(delta.outcome_class, "value") else str(delta.outcome_class),
    }


def deserialize_delta(data: Dict[str, Any]) -> StateDelta:
    """Deserializes a dictionary into a StateDelta dataclass."""
    changed_boxes = [
        (int(b[0]), int(b[1]), int(b[2]), int(b[3]))
        for b in data.get("changed_bounding_boxes", [])
    ]
    return StateDelta(
        added_nodes=list(data.get("added_nodes", [])),
        removed_nodes=list(data.get("removed_nodes", [])),
        modified_nodes=list(data.get("modified_nodes", [])),
        pixel_change_ratio=float(data.get("pixel_change_ratio", 0.0)),
        changed_bounding_boxes=changed_boxes,
        outcome_class=OutcomeClass(data.get("outcome_class", OutcomeClass.SUCCESS.value)),
    )


def transition_to_dict(transition: TransitionTuple) -> Dict[str, Any]:
    """Converts a TransitionTuple to a JSON-compatible dictionary."""
    return {
        "transition_id": transition.transition_id,
        "episode_id": transition.episode_id,
        "step_index": transition.step_index,
        "timestamp_ms": transition.timestamp_ms,
        "ui_state_hash": transition.ui_state_hash,
        "goal_text": transition.goal_text,
        "goal_embedding": list(transition.goal_embedding),
        "visual_embedding": list(transition.visual_embedding) if transition.visual_embedding is not None else None,
        "action": serialize_action(transition.action),
        "next_ui_state_hash": transition.next_ui_state_hash,
        "delta": serialize_delta(transition.delta),
        "duration_ms": transition.duration_ms,
        "surprise_score": transition.surprise_score,
        "provenance": dict(transition.provenance),
    }


def transition_from_dict(data: Dict[str, Any]) -> TransitionTuple:
    """Constructs a TransitionTuple from a dictionary."""
    return TransitionTuple(
        transition_id=data["transition_id"],
        episode_id=data["episode_id"],
        step_index=int(data["step_index"]),
        timestamp_ms=float(data["timestamp_ms"]),
        ui_state_hash=data["ui_state_hash"],
        goal_text=data["goal_text"],
        goal_embedding=[float(x) for x in data["goal_embedding"]],
        visual_embedding=[float(x) for x in data["visual_embedding"]] if data.get("visual_embedding") is not None else None,
        action=deserialize_action(data["action"]),
        next_ui_state_hash=data.get("next_ui_state_hash"),
        delta=deserialize_delta(data["delta"]),
        duration_ms=float(data["duration_ms"]),
        surprise_score=float(data["surprise_score"]),
        provenance=dict(data.get("provenance", {})),
    )


def skill_to_dict(skill: MotorSkill) -> Dict[str, Any]:
    """Converts a MotorSkill to a JSON-compatible dictionary."""
    last_val = (
        skill.last_validated.isoformat()
        if isinstance(skill.last_validated, datetime)
        else str(skill.last_validated)
    )
    return {
        "skill_id": skill.skill_id,
        "version": skill.version,
        "preconditions_hash": skill.preconditions_hash,
        "goal_embedding": list(skill.goal_embedding),
        "visual_context_embedding": list(skill.visual_context_embedding),
        "action_sequence": [serialize_action(a) for a in skill.action_sequence],
        "expected_delta": serialize_delta(skill.expected_delta),
        "timing_mean_ms": skill.timing_mean_ms,
        "timing_std_ms": skill.timing_std_ms,
        "confidence": skill.confidence,
        "safety_class": skill.safety_class.value if hasattr(skill.safety_class, "value") else str(skill.safety_class),
        "provenance_episode_ids": list(skill.provenance_episode_ids),
        "validated_count": skill.validated_count,
        "last_validated": last_val,
    }


def skill_from_dict(data: Dict[str, Any]) -> MotorSkill:
    """Constructs a MotorSkill from a dictionary."""
    last_val_raw = data.get("last_validated")
    if isinstance(last_val_raw, str):
        try:
            last_val = datetime.fromisoformat(last_val_raw)
        except Exception:
            last_val = datetime.now(timezone.utc).replace(tzinfo=None)
    elif isinstance(last_val_raw, datetime):
        last_val = last_val_raw
    else:
        last_val = datetime.now(timezone.utc).replace(tzinfo=None)

    return MotorSkill(
        skill_id=data["skill_id"],
        version=int(data["version"]),
        preconditions_hash=data["preconditions_hash"],
        goal_embedding=[float(x) for x in data["goal_embedding"]],
        visual_context_embedding=[float(x) for x in data["visual_context_embedding"]],
        action_sequence=[deserialize_action(a) for a in data["action_sequence"]],
        expected_delta=deserialize_delta(data["expected_delta"]),
        timing_mean_ms=float(data["timing_mean_ms"]),
        timing_std_ms=float(data["timing_std_ms"]),
        confidence=float(data["confidence"]),
        safety_class=SafetyClass(data.get("safety_class", SafetyClass.REVERSIBLE.value)),
        provenance_episode_ids=list(data.get("provenance_episode_ids", [])),
        validated_count=int(data.get("validated_count", 0)),
        last_validated=last_val,
    )


class FakeMemoryPort(MemoryPort):
    """Deterministic in-memory and SQLite-backed implementation of MemoryPort."""

    def __init__(self, config: Optional[FakeMemoryConfig] = None):
        self.config = config or FakeMemoryConfig()
        self.query_count: int = 0
        self.write_count: int = 0

        # In-memory storage state
        self._transitions_by_id: Dict[str, TransitionTuple] = {}
        self._transitions_by_episode: Dict[str, List[TransitionTuple]] = {}
        self._transitions_by_state: Dict[str, List[TransitionTuple]] = {}
        self._skills_by_id: Dict[str, MotorSkill] = {}
        self._skills_by_preconditions: Dict[str, List[MotorSkill]] = {}

        # SQLite connection
        self._db_conn: Optional[sqlite3.Connection] = None
        if self.config.storage_backend == "sqlite":
            self._init_sqlite()

    def _init_sqlite(self) -> None:
        """Initializes SQLite schema and indexes."""
        db_path = self.config.sqlite_path or ":memory:"
        self._db_conn = sqlite3.connect(db_path, check_same_thread=False)
        self._db_conn.row_factory = sqlite3.Row
        cur = self._db_conn.cursor()

        cur.execute("""
            CREATE TABLE IF NOT EXISTS transitions (
                transition_id TEXT PRIMARY KEY,
                episode_id TEXT NOT NULL,
                step_index INTEGER NOT NULL,
                timestamp_ms REAL NOT NULL,
                ui_state_hash TEXT NOT NULL,
                goal_text TEXT NOT NULL,
                goal_embedding TEXT NOT NULL,
                visual_embedding TEXT,
                action_json TEXT NOT NULL,
                next_ui_state_hash TEXT,
                delta_json TEXT NOT NULL,
                duration_ms REAL NOT NULL,
                surprise_score REAL NOT NULL,
                provenance_json TEXT NOT NULL
            )
        """)

        cur.execute("""
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
            )
        """)

        cur.execute("CREATE INDEX IF NOT EXISTS idx_trans_ep ON transitions(episode_id, step_index)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_trans_state ON transitions(ui_state_hash)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_skills_pre ON skills(preconditions_hash)")
        self._db_conn.commit()

    def set_mode(self, mode: MemoryFaultMode, latency_ms: float = 0.0) -> None:
        """Configures memory fault mode and latency injection."""
        self.config.mode = mode
        self.config.latency_ms = latency_ms

    def reset(self) -> None:
        """Resets all metrics and stored data."""
        self.query_count = 0
        self.write_count = 0
        self._transitions_by_id.clear()
        self._transitions_by_episode.clear()
        self._transitions_by_state.clear()
        self._skills_by_id.clear()
        self._skills_by_preconditions.clear()

        if self._db_conn is not None:
            cur = self._db_conn.cursor()
            cur.execute("DELETE FROM transitions")
            cur.execute("DELETE FROM skills")
            self._db_conn.commit()

    async def _handle_fault(self, is_write: bool = False) -> None:
        """Checks and injects configured fault modes or query latency."""
        if self.config.latency_ms > 0:
            await asyncio.sleep(self.config.latency_ms / 1000.0)

        mode = self.config.mode
        if mode in (MemoryFaultMode.DISCONNECTED, MemoryFaultMode.OUTAGE, MemoryFaultMode.CRASH):
            raise MemoryConnectionError(
                self.config.error_message or f"Simulated Memory Port Failure: {mode.value}"
            )
        if mode == MemoryFaultMode.LOCKED:
            raise MemoryLockError(
                self.config.error_message or "Simulated Database Lock Conflict (SQLITE_BUSY)"
            )
        if is_write and mode == MemoryFaultMode.READ_ONLY:
            raise MemoryReadOnlyError(
                self.config.error_message or "Memory store is configured as read-only"
            )

    async def record_transition(self, transition: TransitionTuple) -> None:
        """Persists a verified transition tuple to the memory store."""
        await self._handle_fault(is_write=True)
        self.write_count += 1

        if self.config.storage_backend == "sqlite" and self._db_conn is not None:
            cur = self._db_conn.cursor()
            cur.execute(
                """
                INSERT OR REPLACE INTO transitions (
                    transition_id, episode_id, step_index, timestamp_ms,
                    ui_state_hash, goal_text, goal_embedding, visual_embedding,
                    action_json, next_ui_state_hash, delta_json, duration_ms,
                    surprise_score, provenance_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    transition.transition_id,
                    transition.episode_id,
                    transition.step_index,
                    transition.timestamp_ms,
                    transition.ui_state_hash,
                    transition.goal_text,
                    json.dumps(transition.goal_embedding),
                    json.dumps(transition.visual_embedding) if transition.visual_embedding is not None else None,
                    json.dumps(serialize_action(transition.action)),
                    transition.next_ui_state_hash,
                    json.dumps(serialize_delta(transition.delta)),
                    transition.duration_ms,
                    transition.surprise_score,
                    json.dumps(transition.provenance),
                ),
            )
            self._db_conn.commit()
            return

        # In-memory storage
        self._transitions_by_id[transition.transition_id] = transition

        # Update episode index
        ep_list = self._transitions_by_episode.setdefault(transition.episode_id, [])
        # replace existing if present
        for idx, item in enumerate(ep_list):
            if item.transition_id == transition.transition_id:
                ep_list[idx] = transition
                break
        else:
            ep_list.append(transition)
        ep_list.sort(key=lambda t: (t.step_index, t.timestamp_ms))

        # Update state index
        st_list = self._transitions_by_state.setdefault(transition.ui_state_hash, [])
        for idx, item in enumerate(st_list):
            if item.transition_id == transition.transition_id:
                st_list[idx] = transition
                break
        else:
            st_list.append(transition)

    async def get_episode_transitions(self, episode_id: str) -> List[TransitionTuple]:
        """Retrieves all chronological transitions for a given episode ID."""
        await self._handle_fault(is_write=False)
        self.query_count += 1

        if self.config.storage_backend == "sqlite" and self._db_conn is not None:
            cur = self._db_conn.cursor()
            cur.execute(
                "SELECT * FROM transitions WHERE episode_id = ? ORDER BY step_index ASC, timestamp_ms ASC",
                (episode_id,),
            )
            rows = cur.fetchall()
            return [self._row_to_transition(r) for r in rows]

        return list(self._transitions_by_episode.get(episode_id, []))

    async def find_transitions_by_state(self, state_hash: str) -> List[TransitionTuple]:
        """Retrieves historical transitions originating from a specific UI state hash."""
        await self._handle_fault(is_write=False)
        self.query_count += 1

        if self.config.storage_backend == "sqlite" and self._db_conn is not None:
            cur = self._db_conn.cursor()
            cur.execute(
                "SELECT * FROM transitions WHERE ui_state_hash = ? ORDER BY timestamp_ms ASC",
                (state_hash,),
            )
            rows = cur.fetchall()
            return [self._row_to_transition(r) for r in rows]

        return list(self._transitions_by_state.get(state_hash, []))

    async def save_skill(self, skill: MotorSkill) -> None:
        """Saves or updates a compiled MotorSkill in the store."""
        await self._handle_fault(is_write=True)
        self.write_count += 1

        if self.config.storage_backend == "sqlite" and self._db_conn is not None:
            cur = self._db_conn.cursor()
            cur.execute(
                """
                INSERT OR REPLACE INTO skills (
                    skill_id, version, preconditions_hash, goal_embedding,
                    visual_context_embedding, action_sequence_json,
                    expected_delta_json, timing_mean_ms, timing_std_ms,
                    confidence, safety_class, provenance_episode_ids_json,
                    validated_count, last_validated
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    skill.skill_id,
                    skill.version,
                    skill.preconditions_hash,
                    json.dumps(skill.goal_embedding),
                    json.dumps(skill.visual_context_embedding),
                    json.dumps([serialize_action(a) for a in skill.action_sequence]),
                    json.dumps(serialize_delta(skill.expected_delta)),
                    skill.timing_mean_ms,
                    skill.timing_std_ms,
                    skill.confidence,
                    skill.safety_class.value if hasattr(skill.safety_class, "value") else str(skill.safety_class),
                    json.dumps(skill.provenance_episode_ids),
                    skill.validated_count,
                    skill.last_validated.isoformat() if isinstance(skill.last_validated, datetime) else str(skill.last_validated),
                ),
            )
            self._db_conn.commit()
            return

        # In-memory storage
        self._skills_by_id[skill.skill_id] = skill
        pre_list = self._skills_by_preconditions.setdefault(skill.preconditions_hash, [])
        for idx, item in enumerate(pre_list):
            if item.skill_id == skill.skill_id:
                pre_list[idx] = skill
                break
        else:
            pre_list.append(skill)

    async def get_skill(self, skill_id: str) -> Optional[MotorSkill]:
        """Retrieves a skill by its unique identifier."""
        await self._handle_fault(is_write=False)
        self.query_count += 1

        if self.config.storage_backend == "sqlite" and self._db_conn is not None:
            cur = self._db_conn.cursor()
            cur.execute("SELECT * FROM skills WHERE skill_id = ?", (skill_id,))
            row = cur.fetchone()
            if row is None:
                return None
            return self._row_to_skill(row)

        return self._skills_by_id.get(skill_id)

    async def find_skills_by_preconditions(self, preconditions_hash: str) -> List[MotorSkill]:
        """Retrieves skills matching a given preconditions structural hash."""
        await self._handle_fault(is_write=False)
        self.query_count += 1

        if self.config.storage_backend == "sqlite" and self._db_conn is not None:
            cur = self._db_conn.cursor()
            cur.execute(
                "SELECT * FROM skills WHERE preconditions_hash = ? ORDER BY confidence DESC",
                (preconditions_hash,),
            )
            rows = cur.fetchall()
            return [self._row_to_skill(r) for r in rows]

        return list(self._skills_by_preconditions.get(preconditions_hash, []))

    async def list_skills(self) -> List[MotorSkill]:
        """Retrieves all stored motor skills."""
        await self._handle_fault(is_write=False)
        self.query_count += 1

        if self.config.storage_backend == "sqlite" and self._db_conn is not None:
            cur = self._db_conn.cursor()
            cur.execute("SELECT * FROM skills ORDER BY skill_id ASC")
            rows = cur.fetchall()
            return [self._row_to_skill(r) for r in rows]

        return list(self._skills_by_id.values())

    async def close(self) -> None:
        """Closes SQLite connection if active."""
        if self._db_conn is not None:
            self._db_conn.close()
            self._db_conn = None

    def _row_to_transition(self, row: sqlite3.Row) -> TransitionTuple:
        """Converts an SQLite row to a TransitionTuple."""
        return TransitionTuple(
            transition_id=row["transition_id"],
            episode_id=row["episode_id"],
            step_index=int(row["step_index"]),
            timestamp_ms=float(row["timestamp_ms"]),
            ui_state_hash=row["ui_state_hash"],
            goal_text=row["goal_text"],
            goal_embedding=json.loads(row["goal_embedding"]),
            visual_embedding=json.loads(row["visual_embedding"]) if row["visual_embedding"] is not None else None,
            action=deserialize_action(json.loads(row["action_json"])),
            next_ui_state_hash=row["next_ui_state_hash"],
            delta=deserialize_delta(json.loads(row["delta_json"])),
            duration_ms=float(row["duration_ms"]),
            surprise_score=float(row["surprise_score"]),
            provenance=json.loads(row["provenance_json"]),
        )

    def _row_to_skill(self, row: sqlite3.Row) -> MotorSkill:
        """Converts an SQLite row to a MotorSkill."""
        raw_actions = json.loads(row["action_sequence_json"])
        action_seq = [deserialize_action(a) for a in raw_actions]
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
            expected_delta=deserialize_delta(json.loads(row["expected_delta_json"])),
            timing_mean_ms=float(row["timing_mean_ms"]),
            timing_std_ms=float(row["timing_std_ms"]),
            confidence=float(row["confidence"]),
            safety_class=SafetyClass(row["safety_class"]),
            provenance_episode_ids=json.loads(row["provenance_episode_ids_json"]),
            validated_count=int(row["validated_count"]),
            last_validated=last_val,
        )
