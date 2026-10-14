"""Reflex–Entorhinal Perception Episode Bridge.

Implements the formal boundary between Reflex perception streaming and Entorhinal
episodic memory journaling (WP-03).

Reflex acquires, normalizes, and diffs sensory observations (zero world model).
Entorhinal persists transitions, tracks temporal context, and verifies predictive state.
"""

from __future__ import annotations

import asyncio
import hashlib
import time
from typing import Any, AsyncIterator, Callable, Dict, List, Optional
import uuid

from reflex.episodes.journal import EpisodeJournalPort, LocalEpisodeJournal
from reflex.ports.observation import ObservationPort
from reflex.schemas.actions import ActionType, TypedAction
from reflex.schemas.delta import OutcomeClass, StateDelta
from reflex.schemas.memory import TransitionTuple
from reflex.schemas.observation import ObservationRecord, PerceptionDelta, PerceptionError


PROTECTED_PROVENANCE_KEYS = frozenset(
    {
        "source_snapshot_id",
        "target_snapshot_id",
        "adapter",
        "platform",
        "quality",
        "semantic_events",
    }
)
"""Provenance keys the bridge alone authors from the bound observations/delta.

Caller-supplied provenance may add extra keys but can never override these:
they are the authoritative source identity of the recorded transition.
"""


UI_STATE_HASH_VERSION = "v1"
"""Version marker for the canonical platform-neutral UI-state hash.

Embedded in the hash preimage (see compute_ui_state_hash), not in the
16-char output. Bumped only by a spec revision in
docs/contract/ui-state-hash-spec.md.
"""

UI_STATE_HASH_TAG = f"reflex-ui-state/{UI_STATE_HASH_VERSION}"
"""Literal preimage tag binding a hash to this spec version."""

UI_STATE_HASH_LENGTH = 16
"""Output length in lowercase hex chars (format unchanged from v0)."""

LEGACY_UI_STATE_HASH_LABEL = "legacy/v0-platform-qualified"
"""Label for pre-fix hashes. Stored legacy values are never recomputed."""


def compute_ui_state_hash_legacy(obs: ObservationRecord) -> str:
    """Pre-fix (v0) UI-state hash: platform label mixed into core identity.

    Retained SOLELY for forensic comparison and regression tests proving the
    CHECK-A leg-(iii) defect and the v0/v1 generation split. New code MUST
    NOT call this: use compute_ui_state_hash.
    """
    raw = f"{obs.platform}:{obs.graph.compute_evidence_hash()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:UI_STATE_HASH_LENGTH]


def compute_ui_state_hash(obs: ObservationRecord) -> str:
    """Computes the canonical platform-neutral hash of the UI observation state.

    Versioned identity per docs/contract/ui-state-hash-spec.md: SHA-256 over
    the preimage ``reflex-ui-state/v1:<evidence-hex>`` (UTF-8), truncated to
    16 hex chars. Depends ONLY on the canonical graph evidence fingerprint,
    so value/state/attribute changes alter episode identity while adapter
    platform labels never do. Format (16 hex chars) is unchanged.
    """
    raw = f"{UI_STATE_HASH_TAG}:{obs.graph.compute_evidence_hash()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:UI_STATE_HASH_LENGTH]


class PerceptionEpisodeBridge:
    """Bridges Reflex ObservationPort emissions into Entorhinal EpisodeJournal records."""

    def __init__(self, journal: EpisodeJournalPort) -> None:
        self.journal = journal

    async def record_transition_from_perception(
        self,
        episode_id: str,
        step_index: int,
        prev_obs: ObservationRecord,
        delta: PerceptionDelta,
        action: TypedAction,
        next_obs: Optional[ObservationRecord] = None,
        goal_text: str = "",
        surprise_score: float = 0.0,
        provenance: Optional[Dict[str, Any]] = None,
    ) -> TransitionTuple:
        """Constructs and records a TransitionTuple from Reflex perception objects.

        Rejects mismatched before/after associations and protected provenance
        conflicts before any journal write: the delta's snapshot IDs must be
        the supplied observations' IDs, and caller provenance may only add
        non-protected keys.
        """
        if delta.source_snapshot_id != prev_obs.observation_id:
            raise PerceptionError(
                "Refusing to record transition: delta.source_snapshot_id "
                f"'{delta.source_snapshot_id}' does not match prev_obs "
                f"'{prev_obs.observation_id}'."
            )
        if next_obs is not None and delta.target_snapshot_id != next_obs.observation_id:
            raise PerceptionError(
                "Refusing to record transition: delta.target_snapshot_id "
                f"'{delta.target_snapshot_id}' does not match next_obs "
                f"'{next_obs.observation_id}'."
            )

        prev_hash = compute_ui_state_hash(prev_obs)
        next_hash = compute_ui_state_hash(next_obs) if next_obs else None

        state_delta = delta.to_state_delta()

        meta_provenance: Dict[str, Any] = {
            "source_snapshot_id": delta.source_snapshot_id,
            "target_snapshot_id": delta.target_snapshot_id,
            "adapter": prev_obs.source_adapter,
            "platform": prev_obs.platform,
            "quality": prev_obs.quality.value,
            "semantic_events": [e.to_dict() for e in delta.semantic_events],
        }
        if provenance:
            for key in PROTECTED_PROVENANCE_KEYS:
                if key in provenance and provenance[key] != meta_provenance[key]:
                    raise PerceptionError(
                        f"Refusing to record transition: caller provenance conflicts "
                        f"with authoritative '{key}'."
                    )
            for key, value in provenance.items():
                if key not in PROTECTED_PROVENANCE_KEYS:
                    meta_provenance[key] = value

        now_ms = delta.timestamp_ms or (time.time() * 1000.0)
        duration_ms = max(0.0, (next_obs.timestamp_ms - prev_obs.timestamp_ms)) if next_obs else 100.0

        transition = TransitionTuple(
            transition_id=f"tx_{episode_id}_{step_index}_{uuid.uuid4().hex[:8]}",
            episode_id=episode_id,
            step_index=step_index,
            timestamp_ms=now_ms,
            ui_state_hash=prev_hash,
            goal_text=goal_text,
            goal_embedding=[0.0] * 8,  # Lightweight default embedding
            visual_embedding=None,
            action=action,
            next_ui_state_hash=next_hash,
            delta=state_delta,
            duration_ms=duration_ms,
            surprise_score=surprise_score,
            provenance=meta_provenance,
        )

        await self.journal.record_transition(transition)
        return transition

    async def stream_and_record_episode(
        self,
        observation_port: ObservationPort,
        episode_id: str,
        goal_text: str = "Observe and record UI state changes",
        interval_ms: float = 50.0,
        max_steps: int = 5,
    ) -> List[TransitionTuple]:
        """Captures exact before/after observation pairs and records one transition per step.

        Each step captures the current observation exactly once and computes the
        delta against the previous step's observation, so the stored delta's
        source/target snapshot IDs are always the recorded before/after pair.
        Recapture around an independent stream is forbidden: it attached deltas
        to observations they were never computed from.
        """
        transitions: List[TransitionTuple] = []
        prev_obs = await observation_port.capture_observation()

        for step in range(max_steps):
            await asyncio.sleep(interval_ms / 1000.0)
            curr_obs = await observation_port.capture_observation()
            ratio, boxes, pixel_status = observation_port.compare_pixel_evidence(
                prev_obs.screenshot_bytes, curr_obs.screenshot_bytes
            )
            delta = observation_port.compute_delta(
                prev_obs, curr_obs,
                pixel_change_ratio=ratio,
                changed_boxes=boxes,
                pixel_status=pixel_status,
            )
            tx = await self.record_transition_from_perception(
                episode_id=episode_id,
                step_index=step,
                prev_obs=prev_obs,
                delta=delta,
                action=TypedAction(action_type=ActionType.NOOP),
                next_obs=curr_obs,
                goal_text=goal_text,
                surprise_score=0.0,
            )
            transitions.append(tx)
            prev_obs = curr_obs

        return transitions
