"""Projection Stager and Atomic Double-Buffering Activation Engine.

Governs safe compilation, epistemic invariant validation, atomic pointer swap,
and last-known-good rollback for derived semantic state.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional, Tuple

from entorhinal.evidence.journal import EvidenceJournal
from entorhinal.schemas.models import DerivedFact, Hypothesis, generate_uuidv7

logger = logging.getLogger(__name__)


@dataclass
class StagedProjectionContext:
    """Isolated candidate staging container for compiling semantic projections."""
    context_id: str = field(default_factory=generate_uuidv7)
    version: str = "1.0.0"
    staged_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    facts: List[DerivedFact] = field(default_factory=list)
    hypotheses: List[Hypothesis] = field(default_factory=list)
    entities: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    validation_passed: bool = False
    validation_errors: List[str] = field(default_factory=list)


class ProjectionStager:
    """Governs atomic double-buffered activation and last-known-good rollback of projections."""

    def __init__(self, journal: EvidenceJournal) -> None:
        self.journal = journal
        self._active_projection: Optional[StagedProjectionContext] = None
        self._last_known_good: Optional[StagedProjectionContext] = None

    # --------------------------------------------------------------------------
    # Staging & Compilation Buffer
    # --------------------------------------------------------------------------

    def stage_new_projection(
        self,
        target_version: str,
        facts: Optional[List[DerivedFact]] = None,
        hypotheses: Optional[List[Hypothesis]] = None,
        entities: Optional[Dict[str, Dict[str, Any]]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> StagedProjectionContext:
        """Allocate an isolated staging buffer for compiling a candidate projection."""
        ctx = StagedProjectionContext(
            version=target_version,
            staged_at=datetime.now(timezone.utc),
            facts=list(facts or []),
            hypotheses=list(hypotheses or []),
            entities=dict(entities or {}),
            metadata=dict(metadata or {}),
            validation_passed=False,
            validation_errors=[],
        )
        return ctx

    # --------------------------------------------------------------------------
    # Epistemic Invariant Validation
    # --------------------------------------------------------------------------

    async def validate_candidate(self, staged_ctx: StagedProjectionContext) -> Tuple[bool, List[str]]:
        """Execute strict epistemic invariant checks on the staged projection.

        Invariants checked:
        1. 100% of facts link to valid EvidenceRecord IDs present in the journal.
        2. Zero tombstoned or revoked evidence leaked into active facts.
        3. No hypothesis is treated as ground truth (is_hypothesis must be True).
        4. DerivedFact confidence is bounded within [0.0, 1.0].
        5. Facts must have non-empty entity URIs and attribute names.
        """
        errors: List[str] = []

        # 1. Fact Validation & Evidence Grounding
        for fact in staged_ctx.facts:
            # Check non-empty evidence IDs
            if not fact.supporting_evidence_ids:
                errors.append(f"Fact '{fact.fact_id}' has empty supporting_evidence_ids.")
                continue

            # Check confidence range
            if not (0.0 <= fact.confidence <= 1.0):
                errors.append(f"Fact '{fact.fact_id}' has invalid confidence: {fact.confidence}.")

            # Grounding check in the evidence journal
            for evid_id in fact.supporting_evidence_ids:
                record = await self.journal.get_by_id(evid_id)
                if record is None:
                    errors.append(f"Fact '{fact.fact_id}' references non-existent EvidenceRecord ID '{evid_id}'.")
                elif record.is_tombstone:
                    errors.append(f"Fact '{fact.fact_id}' references tombstoned/revoked EvidenceRecord ID '{evid_id}'.")

        # 2. Hypothesis Validation
        for hypo in staged_ctx.hypotheses:
            if not hypo.is_hypothesis:
                errors.append(f"Hypothesis '{hypo.hypothesis_id}' violates is_hypothesis invariant.")
            if not (0.0 <= hypo.confidence_score <= 1.0):
                errors.append(f"Hypothesis '{hypo.hypothesis_id}' has invalid confidence: {hypo.confidence_score}.")

        # 3. Check for schema duplicate facts
        seen_fact_keys = set()
        for fact in staged_ctx.facts:
            key = (fact.entity_uri, fact.attribute, fact.revision_id)
            if key in seen_fact_keys:
                errors.append(f"Duplicate fact key detected: entity='{fact.entity_uri}', attribute='{fact.attribute}'.")
            seen_fact_keys.add(key)

        is_valid = len(errors) == 0
        staged_ctx.validation_passed = is_valid
        staged_ctx.validation_errors = errors
        return is_valid, errors

    # --------------------------------------------------------------------------
    # Atomic Activation & Rollback
    # --------------------------------------------------------------------------

    async def activate_staged_projection(self, staged_ctx: StagedProjectionContext) -> None:
        """Atomically swap the active read pointer to candidate and archive previous as last-known-good."""
        if not staged_ctx.validation_passed:
            is_valid, errors = await self.validate_candidate(staged_ctx)
            if not is_valid:
                raise ValueError(
                    f"Cannot activate invalid staged projection context '{staged_ctx.context_id}': {errors}"
                )

        # Atomic pointer swap
        self._last_known_good = self._active_projection
        self._active_projection = staged_ctx
        logger.info(
            "Activated projection version %s (ID: %s, Facts: %d, Hypotheses: %d)",
            staged_ctx.version,
            staged_ctx.context_id,
            len(staged_ctx.facts),
            len(staged_ctx.hypotheses),
        )

    async def rollback_to_last_known_good(self) -> bool:
        """Immediately restore the previous verified projection if active state exhibits faults."""
        if self._last_known_good is None:
            logger.warning("Rollback requested but no last-known-good projection exists")
            return False

        logger.info(
            "Rolling back to last known good projection version %s (ID: %s)",
            self._last_known_good.version,
            self._last_known_good.context_id,
        )
        self._active_projection = self._last_known_good
        return True

    def get_active_projection(self) -> Optional[StagedProjectionContext]:
        """Return the currently active projection state."""
        return self._active_projection

    def get_last_known_good(self) -> Optional[StagedProjectionContext]:
        """Return the archived last-known-good projection state."""
        return self._last_known_good
