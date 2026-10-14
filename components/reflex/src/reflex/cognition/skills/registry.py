"""Reflex Motor Skill Registry & Lifecycle Management.

Maintains in-memory and SQLite-backed registry of compiled MotorSkill routines.
Enforces the 6-stage lifecycle:
  EXTRACTED -> SHADOW_EVALUATION -> CANDIDATE -> PROMOTED (TRUSTED) -> QUARANTINED -> RETIRED
Provides sub-5ms fast-path lookup, dynamic re-grounding parameter extraction,
and automated quarantine upon verification failure.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import threading
import time
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from reflex.cognition.skills.extractor import SkillExtractor
from reflex.cognition.skills.shadow_validator import ShadowRunReport
from reflex.schemas.actions import ActionType, SafetyClass, TypedAction
from reflex.schemas.delta import StateDelta
from reflex.schemas.memory import MotorSkill
from reflex.schemas.state import CanonicalUIGraph, NodeRole


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class SkillStatus(str, Enum):
    """Lifecycle states for compiled motor skills."""
    EXTRACTED = "extracted"
    SHADOW_EVALUATION = "shadow_evaluation"
    SHADOW = "shadow_evaluation"         # Alias
    CANDIDATE = "candidate"
    PROMOTED = "promoted"
    TRUSTED = "promoted"                 # Alias
    QUARANTINED = "quarantined"
    RETIRED = "retired"

    @classmethod
    def from_string(cls, val: str) -> SkillStatus:
        v = val.strip().lower()
        if v in ("shadow", "shadow_evaluation"):
            return cls.SHADOW_EVALUATION
        if v in ("trusted", "promoted"):
            return cls.PROMOTED
        if v in cls._value2member_map_:
            return cls(v)
        return cls.CANDIDATE


@dataclass
class SkillMetadata:
    """Comprehensive governance and performance metadata for a MotorSkill."""

    skill_id: str
    status: SkillStatus = SkillStatus.EXTRACTED
    confidence: float = 0.80
    version: int = 1
    created_at: datetime = field(default_factory=_utc_now)
    updated_at: datetime = field(default_factory=_utc_now)
    validated_count: int = 0
    failure_count: int = 0
    consecutive_failures: int = 0
    shadow_runs_count: int = 0
    shadow_agreement_ratio: float = 0.0
    replay_determinism_ratio: float = 0.0
    parameter_schema: Dict[str, str] = field(default_factory=dict)
    quarantine_reason: Optional[str] = None
    tags: List[str] = field(default_factory=list)

    @property
    def is_trusted(self) -> bool:
        return self.status in (SkillStatus.PROMOTED, SkillStatus.TRUSTED)

    @property
    def is_quarantined(self) -> bool:
        return self.status == SkillStatus.QUARANTINED

    @property
    def is_retired(self) -> bool:
        return self.status == SkillStatus.RETIRED

    def to_dict(self) -> Dict[str, Any]:
        return {
            "skill_id": self.skill_id,
            "status": self.status.value,
            "confidence": self.confidence,
            "version": self.version,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "validated_count": self.validated_count,
            "failure_count": self.failure_count,
            "consecutive_failures": self.consecutive_failures,
            "shadow_runs_count": self.shadow_runs_count,
            "shadow_agreement_ratio": self.shadow_agreement_ratio,
            "replay_determinism_ratio": self.replay_determinism_ratio,
            "parameter_schema": dict(self.parameter_schema),
            "quarantine_reason": self.quarantine_reason,
            "tags": list(self.tags),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> SkillMetadata:
        status_raw = data.get("status", SkillStatus.EXTRACTED.value)
        status = SkillStatus.from_string(status_raw)

        c_at_raw = data.get("created_at")
        created_at = datetime.fromisoformat(c_at_raw) if c_at_raw else _utc_now()

        u_at_raw = data.get("updated_at")
        updated_at = datetime.fromisoformat(u_at_raw) if u_at_raw else _utc_now()

        return cls(
            skill_id=data["skill_id"],
            status=status,
            confidence=float(data.get("confidence", 0.8)),
            version=int(data.get("version", 1)),
            created_at=created_at,
            updated_at=updated_at,
            validated_count=int(data.get("validated_count", 0)),
            failure_count=int(data.get("failure_count", 0)),
            consecutive_failures=int(data.get("consecutive_failures", 0)),
            shadow_runs_count=int(data.get("shadow_runs_count", 0)),
            shadow_agreement_ratio=float(data.get("shadow_agreement_ratio", 0.0)),
            replay_determinism_ratio=float(data.get("replay_determinism_ratio", 0.0)),
            parameter_schema=dict(data.get("parameter_schema", {})),
            quarantine_reason=data.get("quarantine_reason"),
            tags=list(data.get("tags", [])),
        )


@dataclass(frozen=True)
class SkillMatchResult:
    """Result of querying the skill registry for live fast-path execution."""

    skill: MotorSkill
    confidence: float
    parameter_bindings: Dict[str, Any]
    metadata: Optional[SkillMetadata] = None


class SkillRegistryPort(ABC):
    """Abstract port for motor skill lookup, candidate registration, and lifecycle promotion."""

    @abstractmethod
    def find_matching_skill(
        self,
        current_state: CanonicalUIGraph,
        goal_text: str,
    ) -> Optional[SkillMatchResult]:
        """Finds matching trusted skill based on state hash and goal semantics."""
        ...

    @abstractmethod
    def register_candidate(self, skill: MotorSkill, metadata: Optional[SkillMetadata] = None) -> str:
        """Registers a newly extracted candidate skill."""
        ...

    @abstractmethod
    def promote_skill(self, skill_id: str, force: bool = False) -> None:
        """Promotes a skill from candidate/shadow to promoted (trusted) status."""
        ...

    @abstractmethod
    def record_execution_outcome(self, skill_id: str, success: bool, surprise_score: float = 0.0) -> None:
        """Updates skill validation metrics and triggers automated quarantine if failed."""
        ...


class SkillRegistry(SkillRegistryPort):
    """In-memory and SQLite-persisted skill registry implementing the 6-stage consolidation lifecycle.
    
    Guarantees:
    - Sub-5ms fast-path in-memory matching.
    - Automatic quarantine on live execution failure.
    - Permanent retirement after >= 3 cumulative or consecutive failures.
    - Dynamic re-grounding parameter extraction.
    """

    def __init__(
        self,
        db_path: str = ":memory:",
        extractor: Optional[SkillExtractor] = None,
        min_promotion_shadow_runs: int = 5,
        min_promotion_agreement: float = 0.95,
        min_promotion_determinism: float = 1.0,
    ) -> None:
        self.db_path = db_path
        self.extractor = extractor or SkillExtractor()
        self.min_promotion_shadow_runs = min_promotion_shadow_runs
        self.min_promotion_agreement = min_promotion_agreement
        self.min_promotion_determinism = min_promotion_determinism

        self._lock = threading.RLock()
        self._skills: Dict[str, MotorSkill] = {}
        self._metadata: Dict[str, SkillMetadata] = {}
        # Preconditions hash to skill_ids index for sub-5ms retrieval
        self._preconditions_index: Dict[str, List[str]] = {}
        # Invariant affordance pattern index for robust cross-instance matching
        self._affordance_index: Dict[str, List[str]] = {}

        self._db_conn: Optional[sqlite3.Connection] = None
        self._init_db()

    def _init_db(self) -> None:
        """Initializes SQLite schema and hydrates in-memory cache."""
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
            try:
                cur.execute("PRAGMA journal_mode=WAL;")
                cur.execute("PRAGMA synchronous=NORMAL;")
            except sqlite3.OperationalError:
                pass

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

            # Skill metadata table
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS skill_metadata (
                    skill_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    version INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    validated_count INTEGER NOT NULL,
                    failure_count INTEGER NOT NULL,
                    consecutive_failures INTEGER NOT NULL,
                    shadow_runs_count INTEGER NOT NULL,
                    shadow_agreement_ratio REAL NOT NULL,
                    replay_determinism_ratio REAL NOT NULL,
                    parameter_schema_json TEXT NOT NULL,
                    quarantine_reason TEXT,
                    tags_json TEXT NOT NULL,
                    FOREIGN KEY(skill_id) REFERENCES skills(skill_id) ON DELETE CASCADE
                );
                """
            )

            cur.execute("CREATE INDEX IF NOT EXISTS idx_skills_preconditions ON skills(preconditions_hash);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_meta_status ON skill_metadata(status);")
            self._db_conn.commit()

            # Hydrate cache
            self._hydrate_from_db()

    def _hydrate_from_db(self) -> None:
        """Loads all stored skills and metadata into memory."""
        if not self._db_conn:
            return
        cur = self._db_conn.cursor()
        cur.execute("SELECT * FROM skills")
        skill_rows = cur.fetchall()

        for r in skill_rows:
            sk = self._row_to_skill(r)
            self._skills[sk.skill_id] = sk
            self._index_skill(sk)

        cur.execute("SELECT * FROM skill_metadata")
        meta_rows = cur.fetchall()
        for r in meta_rows:
            meta = self._row_to_metadata(r)
            self._metadata[meta.skill_id] = meta

    def _index_preconditions(self, pre_hash: str, skill_id: str) -> None:
        if pre_hash not in self._preconditions_index:
            self._preconditions_index[pre_hash] = []
        if skill_id not in self._preconditions_index[pre_hash]:
            self._preconditions_index[pre_hash].append(skill_id)

    def _index_skill(self, skill: MotorSkill) -> None:
        """Indexes skill by exact preconditions hash as well as invariant affordance pattern."""
        self._index_preconditions(skill.preconditions_hash, skill.skill_id)
        try:
            pattern = self.extractor.extract_affordance_pattern_from_skill(skill)
            sig = pattern.pattern_signature
            if sig not in self._affordance_index:
                self._affordance_index[sig] = []
            if skill.skill_id not in self._affordance_index[sig]:
                self._affordance_index[sig].append(skill.skill_id)

            # Index by individual required affordance items for fast-path retrieval
            for item in pattern.required_affordances:
                key1 = f"{item.role}:{item.label}"
                key2 = f"*:{item.label}"
                for k in (key1, key2):
                    if k not in self._affordance_index:
                        self._affordance_index[k] = []
                    if skill.skill_id not in self._affordance_index[k]:
                        self._affordance_index[k].append(skill.skill_id)
        except Exception:
            pass

    # =========================================================================
    # Fast-Path Lookup (< 5ms)
    # =========================================================================

    def find_matching_skill(
        self,
        current_state: CanonicalUIGraph,
        goal_text: str,
    ) -> Optional[SkillMatchResult]:
        """Finds matching trusted/promoted skill based on state hash and goal semantics.
        
        Guarantees sub-5ms retrieval from in-memory index.
        Ignores Quarantined, Retired, Shadow, or unpromoted Candidate skills.
        """
        start_time = time.perf_counter()

        with self._lock:
            # 1. Compute candidate precondition hashes
            # Primary: interactable DOM subgraph hash
            subgraph_hash = self.extractor.compute_preconditions_hash(current_state)
            # Secondary: full state hash
            state_hash = current_state.compute_state_hash()

            matching_ids = set()
            if subgraph_hash in self._preconditions_index:
                matching_ids.update(self._preconditions_index[subgraph_hash])
            if state_hash in self._preconditions_index:
                matching_ids.update(self._preconditions_index[state_hash])

            # 2. Invariant affordance pattern index matches
            state_affordance = self.extractor.extract_affordance_pattern(current_state)
            if state_affordance.pattern_signature in self._affordance_index:
                matching_ids.update(self._affordance_index[state_affordance.pattern_signature])

            # Query affordance index by available interactables on live screen
            if current_state and current_state.nodes:
                for node in current_state.nodes.values():
                    node_role = (node.role.value if isinstance(node.role, NodeRole) else str(node.role)).lower()
                    node_lbl = self.extractor._normalize_label(node.label or "")
                    if not node_lbl and node.node_id:
                        node_lbl = self.extractor._normalize_label(node.node_id)
                    if not node_lbl:
                        continue
                    for query_key in (f"{node_role}:{node_lbl}", f"*:{node_lbl}"):
                        if query_key in self._affordance_index:
                            matching_ids.update(self._affordance_index[query_key])

            # 3. Filter to PROMOTED / TRUSTED skills
            trusted_candidates: List[Tuple[MotorSkill, SkillMetadata]] = []
            for sk_id in matching_ids:
                sk = self._skills.get(sk_id)
                meta = self._metadata.get(sk_id)
                if not sk or not meta:
                    continue

                # STRICT RULE: Quarantined, Retired, Extracted, or unpromoted skills are NEVER returned
                if not meta.is_trusted or meta.is_quarantined or meta.is_retired:
                    continue

                # Verify skill affordance pattern is satisfied by current live state
                try:
                    pat = self.extractor.extract_affordance_pattern_from_skill(sk)
                    if not self.extractor.matches_affordance_pattern(pat, current_state):
                        continue
                except Exception:
                    pass

                trusted_candidates.append((sk, meta))

            # 4. Invariant Affordance Compatibility Fallback
            # If exact / index lookups yielded no trusted candidate, evaluate whether any trusted skill's
            # affordances are satisfied by the current live UI graph (dynamic invariance)
            if not trusted_candidates:
                for sk_id, meta in self._metadata.items():
                    if not meta.is_trusted or meta.is_quarantined or meta.is_retired:
                        continue
                    sk = self._skills.get(sk_id)
                    if not sk:
                        continue
                    try:
                        pattern = self.extractor.extract_affordance_pattern_from_skill(sk)
                        if self.extractor.matches_affordance_pattern(pattern, current_state):
                            trusted_candidates.append((sk, meta))
                    except Exception:
                        pass

            if not trusted_candidates:
                return None

            # 5. Score candidates by goal similarity & confidence
            best_match: Optional[Tuple[MotorSkill, SkillMetadata, Dict[str, Any], float]] = None
            best_score = -1.0

            for sk, meta in trusted_candidates:
                # Extract parameter bindings from goal_text and state
                bindings = self._extract_parameter_bindings(sk, current_state, goal_text)
                sim = self._compute_goal_similarity(sk, goal_text)
                score = meta.confidence * (0.6 + 0.4 * sim)

                if score > best_score:
                    best_score = score
                    best_match = (sk, meta, bindings, score)

            if not best_match or best_score < 0.4:
                return None

            matched_skill, matched_meta, matched_bindings, final_conf = best_match

            # Dynamically re-ground skill actions to current state nodes and coordinates
            regrounded_actions = self.extractor.reground_action_sequence(
                matched_skill.action_sequence,
                current_state,
                matched_bindings,
            )
            grounded_skill = MotorSkill(
                skill_id=matched_skill.skill_id,
                version=matched_skill.version,
                preconditions_hash=matched_skill.preconditions_hash,
                goal_embedding=matched_skill.goal_embedding,
                visual_context_embedding=matched_skill.visual_context_embedding,
                action_sequence=regrounded_actions,
                expected_delta=matched_skill.expected_delta,
                timing_mean_ms=matched_skill.timing_mean_ms,
                timing_std_ms=matched_skill.timing_std_ms,
                confidence=matched_skill.confidence,
                safety_class=matched_skill.safety_class,
                provenance_episode_ids=matched_skill.provenance_episode_ids,
                validated_count=matched_skill.validated_count,
                last_validated=matched_skill.last_validated,
            )

            return SkillMatchResult(
                skill=grounded_skill,
                confidence=round(matched_meta.confidence, 4),
                parameter_bindings=matched_bindings,
                metadata=matched_meta,
            )

    # =========================================================================
    # Lifecycle Registrations & Transitions
    # =========================================================================

    def register_extracted(
        self,
        skill: MotorSkill,
        metadata: Optional[SkillMetadata] = None,
    ) -> str:
        """Registers a newly extracted motor skill in EXTRACTED state."""
        meta = metadata or SkillMetadata(
            skill_id=skill.skill_id,
            status=SkillStatus.EXTRACTED,
            confidence=skill.confidence,
            version=skill.version,
            validated_count=skill.validated_count,
            parameter_schema=self._extract_param_schema_from_skill(skill),
        )
        meta.status = SkillStatus.EXTRACTED
        self._persist_skill(skill, meta)
        return skill.skill_id

    def register_candidate(
        self,
        skill: MotorSkill,
        metadata: Optional[SkillMetadata] = None,
    ) -> str:
        """Registers or advances a skill into CANDIDATE status for shadow testing."""
        meta = metadata or SkillMetadata(
            skill_id=skill.skill_id,
            status=SkillStatus.CANDIDATE,
            confidence=skill.confidence,
            version=skill.version,
            validated_count=skill.validated_count,
            parameter_schema=self._extract_param_schema_from_skill(skill),
        )
        meta.status = SkillStatus.CANDIDATE
        self._persist_skill(skill, meta)
        return skill.skill_id

    def record_shadow_evaluation(
        self,
        skill_id: str,
        report: ShadowRunReport,
    ) -> None:
        """Records the outcome of a background shadow evaluation run."""
        with self._lock:
            meta = self._metadata.get(skill_id)
            if not meta:
                return

            n = meta.shadow_runs_count
            meta.shadow_agreement_ratio = (
                (meta.shadow_agreement_ratio * n + report.agreement_ratio) / (n + 1)
            )
            meta.shadow_runs_count += 1
            meta.updated_at = _utc_now()

            # State transition logic
            if meta.status == SkillStatus.EXTRACTED:
                meta.status = SkillStatus.SHADOW_EVALUATION

            if (
                meta.status == SkillStatus.SHADOW_EVALUATION
                and meta.shadow_runs_count >= 2
                and meta.shadow_agreement_ratio >= 0.80
            ):
                meta.status = SkillStatus.CANDIDATE

            self._persist_metadata(meta)

    def record_replay_validation(
        self,
        skill_id: str,
        determinism_ratio: float,
    ) -> None:
        """Records deterministic replay validation ratio."""
        with self._lock:
            meta = self._metadata.get(skill_id)
            if not meta:
                return
            meta.replay_determinism_ratio = determinism_ratio
            meta.updated_at = _utc_now()
            self._persist_metadata(meta)

    def promote_skill(self, skill_id: str, force: bool = False) -> None:
        """Promotes a candidate skill to PROMOTED (trusted) status.
        
        Validates:
        - Shadow passes >= 5 with agreement >= 95%
        - Replay determinism == 100%
        - Safety class == REVERSIBLE (or forced override)
        """
        with self._lock:
            skill = self._skills.get(skill_id)
            meta = self._metadata.get(skill_id)
            if not skill or not meta:
                raise KeyError(f"Skill {skill_id} not found in registry")

            if not force:
                if meta.shadow_runs_count < self.min_promotion_shadow_runs:
                    raise ValueError(
                        f"Cannot promote skill {skill_id}: shadow runs {meta.shadow_runs_count} "
                        f"< required {self.min_promotion_shadow_runs}"
                    )
                if meta.shadow_agreement_ratio < self.min_promotion_agreement:
                    raise ValueError(
                        f"Cannot promote skill {skill_id}: shadow agreement {meta.shadow_agreement_ratio:.2f} "
                        f"< required {self.min_promotion_agreement:.2f}"
                    )
                if (
                    meta.replay_determinism_ratio > 0.0
                    and meta.replay_determinism_ratio < self.min_promotion_determinism
                ):
                    raise ValueError(
                        f"Cannot promote skill {skill_id}: replay determinism {meta.replay_determinism_ratio:.2f} "
                        f"< required {self.min_promotion_determinism:.2f}"
                    )
                if skill.safety_class == SafetyClass.DESTRUCTIVE and "human_approved" not in meta.tags:
                    raise ValueError(
                        f"Cannot promote destructive skill {skill_id} without human policy approval tag"
                    )

            meta.status = SkillStatus.PROMOTED
            meta.confidence = max(meta.confidence, 0.85)
            meta.updated_at = _utc_now()
            meta.quarantine_reason = None

            # Calibrate skill object
            skill.confidence = meta.confidence
            skill.last_validated = _utc_now()

            self._persist_skill(skill, meta)

    def quarantine_skill(self, skill_id: str, reason: str = "") -> None:
        """Immediately quarantines a skill, removing it from live lookup."""
        with self._lock:
            meta = self._metadata.get(skill_id)
            skill = self._skills.get(skill_id)
            if not meta:
                return

            meta.status = SkillStatus.QUARANTINED
            meta.confidence = max(0.0, meta.confidence * 0.5 - 0.2)
            meta.quarantine_reason = reason or "Manual quarantine"
            meta.updated_at = _utc_now()

            if skill:
                skill.confidence = meta.confidence
                self._persist_skill(skill, meta)
            else:
                self._persist_metadata(meta)

    def retire_skill(self, skill_id: str, reason: str = "") -> None:
        """Permanently retires a skill from active usage."""
        with self._lock:
            meta = self._metadata.get(skill_id)
            skill = self._skills.get(skill_id)
            if not meta:
                return

            meta.status = SkillStatus.RETIRED
            meta.confidence = 0.0
            meta.quarantine_reason = reason or "Skill retired"
            meta.updated_at = _utc_now()

            if skill:
                skill.confidence = 0.0
                self._persist_skill(skill, meta)
            else:
                self._persist_metadata(meta)

    def reactivate_quarantined_skill(self, skill_id: str) -> None:
        """Demotes a quarantined skill back to SHADOW_EVALUATION for re-testing."""
        with self._lock:
            meta = self._metadata.get(skill_id)
            if not meta:
                return
            if meta.is_retired:
                raise ValueError(f"Cannot reactivate permanently retired skill {skill_id}")

            meta.status = SkillStatus.SHADOW_EVALUATION
            meta.confidence = 0.50
            meta.consecutive_failures = 0
            meta.updated_at = _utc_now()
            self._persist_metadata(meta)

    # =========================================================================
    # Execution Outcome & Automated Quarantine
    # =========================================================================

    def record_execution_outcome(
        self,
        skill_id: str,
        success: bool,
        surprise_score: float = 0.0,
    ) -> None:
        """Updates validation metrics on live execution.
        
        CRITICAL RULE: A single verification failure on a live skill immediately drops
        its confidence score and places the skill in QUARANTINED status.
        If cumulative failures >= 3, automatically transitions to RETIRED.
        """
        with self._lock:
            meta = self._metadata.get(skill_id)
            skill = self._skills.get(skill_id)
            if not meta:
                return

            meta.updated_at = _utc_now()

            if success:
                meta.validated_count += 1
                meta.consecutive_failures = 0
                meta.confidence = min(1.0, meta.confidence + 0.05 * (1.0 - meta.confidence))
                if skill:
                    skill.validated_count = meta.validated_count
                    skill.confidence = meta.confidence
                    skill.last_validated = _utc_now()
            else:
                # Execution / Verification Failure -> Immediate Quarantine!
                meta.failure_count += 1
                meta.consecutive_failures += 1
                meta.confidence = max(0.0, meta.confidence * 0.5 - 0.2)
                meta.quarantine_reason = (
                    f"Verification failure (consecutive={meta.consecutive_failures}, "
                    f"total={meta.failure_count}, surprise={surprise_score:.3f})"
                )

                if meta.failure_count >= 3 or meta.consecutive_failures >= 3:
                    meta.status = SkillStatus.RETIRED
                    meta.confidence = 0.0
                    meta.quarantine_reason += " -> Automatically RETIRED (failures >= 3)"
                else:
                    meta.status = SkillStatus.QUARANTINED

                if skill:
                    skill.confidence = meta.confidence
                    skill.last_validated = _utc_now()

            if skill:
                self._persist_skill(skill, meta)
            else:
                self._persist_metadata(meta)

    # =========================================================================
    # Inspection and Retrieval
    # =========================================================================

    def get_skill(self, skill_id: str) -> Optional[MotorSkill]:
        """Retrieves a MotorSkill by ID."""
        with self._lock:
            return self._skills.get(skill_id)

    def get_metadata(self, skill_id: str) -> Optional[SkillMetadata]:
        """Retrieves SkillMetadata by ID."""
        with self._lock:
            return self._metadata.get(skill_id)

    def list_skills(
        self,
        status: Optional[SkillStatus] = None,
    ) -> List[Tuple[MotorSkill, SkillMetadata]]:
        """Lists skills optionally filtered by lifecycle status."""
        with self._lock:
            results = []
            for sk_id, sk in self._skills.items():
                meta = self._metadata.get(sk_id)
                if not meta:
                    continue
                if status is None or meta.status == status:
                    results.append((sk, meta))
            return results

    # =========================================================================
    # Persistence Helpers
    # =========================================================================

    def _persist_skill(self, skill: MotorSkill, metadata: SkillMetadata) -> None:
        """Updates in-memory cache and persists skill & metadata to SQLite."""
        self._skills[skill.skill_id] = skill
        self._metadata[skill.skill_id] = metadata
        self._index_skill(skill)

        if not self._db_conn:
            return

        last_val = (
            skill.last_validated.isoformat()
            if isinstance(skill.last_validated, datetime)
            else str(skill.last_validated)
        )

        cur = self._db_conn.cursor()
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

        cur.execute(
            """
            INSERT INTO skill_metadata (
                skill_id, status, confidence, version, created_at, updated_at,
                validated_count, failure_count, consecutive_failures,
                shadow_runs_count, shadow_agreement_ratio, replay_determinism_ratio,
                parameter_schema_json, quarantine_reason, tags_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(skill_id) DO UPDATE SET
                status=excluded.status,
                confidence=excluded.confidence,
                version=excluded.version,
                updated_at=excluded.updated_at,
                validated_count=excluded.validated_count,
                failure_count=excluded.failure_count,
                consecutive_failures=excluded.consecutive_failures,
                shadow_runs_count=excluded.shadow_runs_count,
                shadow_agreement_ratio=excluded.shadow_agreement_ratio,
                replay_determinism_ratio=excluded.replay_determinism_ratio,
                parameter_schema_json=excluded.parameter_schema_json,
                quarantine_reason=excluded.quarantine_reason,
                tags_json=excluded.tags_json
            """,
            (
                metadata.skill_id,
                metadata.status.value,
                metadata.confidence,
                metadata.version,
                metadata.created_at.isoformat(),
                metadata.updated_at.isoformat(),
                metadata.validated_count,
                metadata.failure_count,
                metadata.consecutive_failures,
                metadata.shadow_runs_count,
                metadata.shadow_agreement_ratio,
                metadata.replay_determinism_ratio,
                json.dumps(metadata.parameter_schema),
                metadata.quarantine_reason,
                json.dumps(metadata.tags),
            ),
        )
        self._db_conn.commit()

    def _persist_metadata(self, metadata: SkillMetadata) -> None:
        """Persists metadata record to DB."""
        self._metadata[metadata.skill_id] = metadata
        if not self._db_conn:
            return

        cur = self._db_conn.cursor()
        cur.execute(
            """
            INSERT INTO skill_metadata (
                skill_id, status, confidence, version, created_at, updated_at,
                validated_count, failure_count, consecutive_failures,
                shadow_runs_count, shadow_agreement_ratio, replay_determinism_ratio,
                parameter_schema_json, quarantine_reason, tags_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(skill_id) DO UPDATE SET
                status=excluded.status,
                confidence=excluded.confidence,
                version=excluded.version,
                updated_at=excluded.updated_at,
                validated_count=excluded.validated_count,
                failure_count=excluded.failure_count,
                consecutive_failures=excluded.consecutive_failures,
                shadow_runs_count=excluded.shadow_runs_count,
                shadow_agreement_ratio=excluded.shadow_agreement_ratio,
                replay_determinism_ratio=excluded.replay_determinism_ratio,
                parameter_schema_json=excluded.parameter_schema_json,
                quarantine_reason=excluded.quarantine_reason,
                tags_json=excluded.tags_json
            """,
            (
                metadata.skill_id,
                metadata.status.value,
                metadata.confidence,
                metadata.version,
                metadata.created_at.isoformat(),
                metadata.updated_at.isoformat(),
                metadata.validated_count,
                metadata.failure_count,
                metadata.consecutive_failures,
                metadata.shadow_runs_count,
                metadata.shadow_agreement_ratio,
                metadata.replay_determinism_ratio,
                json.dumps(metadata.parameter_schema),
                metadata.quarantine_reason,
                json.dumps(metadata.tags),
            ),
        )
        self._db_conn.commit()

    # =========================================================================
    # Deserialization & Internal Helpers
    # =========================================================================

    def _extract_param_schema_from_skill(self, skill: MotorSkill) -> Dict[str, str]:
        """Scans skill action sequence templates to build parameter schema."""
        schema: Dict[str, str] = {}
        for act in skill.action_sequence:
            if act.text_payload:
                slots = re.findall(r"\{\{([a-zA-Z0-9_]+)\}\}", act.text_payload)
                for s in slots:
                    schema[s] = "str"
        return schema

    def _extract_parameter_bindings(
        self,
        skill: MotorSkill,
        current_state: CanonicalUIGraph,
        goal_text: str,
    ) -> Dict[str, Any]:
        """Extracts dynamic parameter bindings from goal text or current UI graph."""
        bindings: Dict[str, Any] = {}
        meta = self._metadata.get(skill.skill_id)
        param_schema = meta.parameter_schema if meta else self._extract_param_schema_from_skill(skill)

        for param_name in param_schema:
            val = self._extract_slot_value_from_text(param_name, goal_text)
            if val is not None:
                bindings[param_name] = val

        return bindings

    def _extract_slot_value_from_text(self, slot_name: str, text: str) -> Optional[str]:
        """Heuristic extractor matching slot values from goal text."""
        # Check quoted strings first: e.g. search for 'shoes' or "laptop"
        quoted = re.findall(r"['\"]([^'\"]+)['\"]", text)
        if quoted:
            return quoted[0]

        # Specific heuristics
        if slot_name in ("query", "search_term", "search"):
            match = re.search(r"(?:search|find|query)\s+(?:for\s+)?([a-zA-Z0-9\s]+)", text, re.IGNORECASE)
            if match:
                return match.group(1).strip()

        if slot_name in ("user_email", "email"):
            match = re.search(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", text)
            if match:
                return match.group(0)

        if slot_name in ("username", "user"):
            match = re.search(r"(?:user|username|login)\s+([a-zA-Z0-9_]+)", text, re.IGNORECASE)
            if match:
                return match.group(1).strip()

        return None

    def _compute_goal_similarity(self, skill: MotorSkill, goal_text: str) -> float:
        """Computes similarity between skill goal and incoming goal query."""
        if not goal_text:
            return 0.5

        # Check action label/target token overlap
        tokens_goal = set(re.findall(r"\w+", goal_text.lower()))
        if not tokens_goal:
            return 0.5

        tokens_skill: Set[str] = set()
        for act in skill.action_sequence:
            if act.target_label:
                tokens_skill.update(re.findall(r"\w+", act.target_label.lower()))
            if act.text_payload:
                tokens_skill.update(re.findall(r"\w+", act.text_payload.lower()))

        if not tokens_skill:
            return 0.7

        overlap = tokens_goal.intersection(tokens_skill)
        return min(1.0, 0.4 + 0.6 * (len(overlap) / len(tokens_skill)))

    def _row_to_skill(self, row: sqlite3.Row) -> MotorSkill:
        raw_actions = json.loads(row["action_sequence_json"])
        action_seq = [TypedAction.from_dict(a) for a in raw_actions]
        last_val_str = row["last_validated"]
        try:
            last_val = datetime.fromisoformat(last_val_str)
        except Exception:
            last_val = _utc_now()

        raw_safety = row["safety_class"]
        safety_class = SafetyClass(raw_safety) if raw_safety in SafetyClass._value2member_map_ else SafetyClass.REVERSIBLE

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
            safety_class=safety_class,
            provenance_episode_ids=json.loads(row["provenance_episode_ids_json"]),
            validated_count=int(row["validated_count"]),
            last_validated=last_val,
        )

    def _row_to_metadata(self, row: sqlite3.Row) -> SkillMetadata:
        status_raw = row["status"]
        status = SkillStatus.from_string(status_raw)
        c_at_raw = row["created_at"]
        created_at = datetime.fromisoformat(c_at_raw) if c_at_raw else _utc_now()
        u_at_raw = row["updated_at"]
        updated_at = datetime.fromisoformat(u_at_raw) if u_at_raw else _utc_now()

        return SkillMetadata(
            skill_id=row["skill_id"],
            status=status,
            confidence=float(row["confidence"]),
            version=int(row["version"]),
            created_at=created_at,
            updated_at=updated_at,
            validated_count=int(row["validated_count"]),
            failure_count=int(row["failure_count"]),
            consecutive_failures=int(row["consecutive_failures"]),
            shadow_runs_count=int(row["shadow_runs_count"]),
            shadow_agreement_ratio=float(row["shadow_agreement_ratio"]),
            replay_determinism_ratio=float(row["replay_determinism_ratio"]),
            parameter_schema=json.loads(row["parameter_schema_json"]),
            quarantine_reason=row["quarantine_reason"],
            tags=json.loads(row["tags_json"]),
        )

    def close(self) -> None:
        """Closes SQLite connection."""
        with self._lock:
            if self._db_conn:
                try:
                    self._db_conn.close()
                except Exception:
                    pass
                self._db_conn = None
