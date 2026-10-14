"""Uncertainty Calibration, Drift Detection, and Hypothesis Management Engine.

Implements:
1. UncertaintyEngine:
   - Calibrates confidence scores [0.0, 1.0] with multi-source diversity and temporal decay.
   - Detects semantic drift between consecutive developer sessions.
   - Reconciles conflicting candidate hypotheses.
2. HypothesisManager:
   - Generates candidate intent classifications grounded by candidate EvidenceRecord IDs.
   - Enforces strict epistemic invariant: is_hypothesis=True and confidence < 1.0.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import math
from typing import Any, Dict, List, Optional, Set, Tuple

from entorhinal.projections.models import SessionTaskCluster
from entorhinal.schemas.models import EvidenceRecord, Hypothesis, SourceType, generate_uuidv7


class UncertaintyEngine:
    """Mathematical confidence calibration and drift detection engine."""

    def __init__(
        self,
        evidence_lambda: float = 0.45,
        drift_threshold: float = 0.55,
        max_hypothesis_confidence: float = 0.95,
        min_hypothesis_confidence: float = 0.05,
    ) -> None:
        self.evidence_lambda = evidence_lambda
        self.drift_threshold = drift_threshold
        self.max_hypothesis_confidence = max_hypothesis_confidence
        self.min_hypothesis_confidence = min_hypothesis_confidence

    # --------------------------------------------------------------------------
    # Confidence Calibration
    # --------------------------------------------------------------------------

    def calibrate_confidence(
        self,
        base_prior: float,
        evidence_count: int,
        source_types: Optional[Set[SourceType]] = None,
        age_seconds: float = 0.0,
        half_life_seconds: float = 86400.0,  # 24 hour half life
    ) -> float:
        """Calculate calibrated confidence with evidence saturation and source diversity bonus.

        Formula:
        Score = base_prior * (1 - exp(-lambda * N)) * diversity_multiplier * decay_factor
        Bounded strictly in [min_confidence, max_hypothesis_confidence].
        """
        if evidence_count <= 0:
            return self.min_hypothesis_confidence

        # Evidence count saturation factor: 1 - exp(-lambda * N)
        saturation = 1.0 - math.exp(-self.evidence_lambda * evidence_count)

        # Source diversity bonus (e.g. cross-correlation of IDE + Terminal + Browser)
        diversity_count = len(source_types) if source_types else 1
        diversity_multiplier = min(1.3, 1.0 + (0.10 * (diversity_count - 1)))

        # Temporal decay factor: exp(-ln(2) * age / half_life)
        if age_seconds > 0:
            decay_factor = math.exp(-0.69315 * (age_seconds / half_life_seconds))
        else:
            decay_factor = 1.0

        raw_score = base_prior * saturation * diversity_multiplier * decay_factor
        return round(max(self.min_hypothesis_confidence, min(self.max_hypothesis_confidence, raw_score)), 4)

    # --------------------------------------------------------------------------
    # Drift Detection
    # --------------------------------------------------------------------------

    def detect_drift(
        self,
        cluster_a: SessionTaskCluster,
        cluster_b: SessionTaskCluster,
    ) -> Dict[str, Any]:
        """Measure semantic divergence between two session clusters and flag task drift."""
        vec_a = cluster_a.centroid_terms
        vec_b = cluster_b.centroid_terms

        # Compute cosine distance between term frequency centroids
        dot_product = 0.0
        for term, val in vec_a.items():
            if term in vec_b:
                dot_product += val * vec_b[term]

        similarity = max(0.0, min(1.0, dot_product))
        divergence = 1.0 - similarity

        is_drift = divergence >= self.drift_threshold

        drift_reasons: List[str] = []
        if is_drift:
            drift_reasons.append(
                f"Term divergence {divergence:.3f} exceeds threshold {self.drift_threshold:.3f}"
            )
            if cluster_a.primary_app != cluster_b.primary_app:
                drift_reasons.append(
                    f"Primary tool switched from '{cluster_a.primary_app}' to '{cluster_b.primary_app}'"
                )
            if cluster_a.primary_topic != cluster_b.primary_topic:
                drift_reasons.append(
                    f"Topic shifted from '{cluster_a.primary_topic}' to '{cluster_b.primary_topic}'"
                )

        return {
            "drift_detected": is_drift,
            "divergence_score": round(divergence, 4),
            "similarity_score": round(similarity, 4),
            "cluster_a_id": cluster_a.cluster_id,
            "cluster_b_id": cluster_b.cluster_id,
            "reasons": drift_reasons,
        }

    # --------------------------------------------------------------------------
    # Conflict Resolution
    # --------------------------------------------------------------------------

    def resolve_conflicts(self, candidate_hypotheses: List[Hypothesis]) -> List[Hypothesis]:
        """Rank and resolve competing hypotheses for a given entity or cluster."""
        if not candidate_hypotheses:
            return []

        # Sort descending by calibrated confidence score
        sorted_hypotheses = sorted(
            candidate_hypotheses,
            key=lambda h: h.confidence_score,
            reverse=True,
        )

        return sorted_hypotheses


class HypothesisManager:
    """Generates candidate intent hypotheses with epistemic tags and calibrated uncertainty."""

    def __init__(self, uncertainty_engine: Optional[UncertaintyEngine] = None) -> None:
        self.uncertainty_engine = uncertainty_engine or UncertaintyEngine()

    def propose_intent(
        self,
        cluster: SessionTaskCluster,
        supporting_records: Optional[List[EvidenceRecord]] = None,
        default_ttl_seconds: int = 3600,
    ) -> List[Hypothesis]:
        """Synthesize candidate intent classifications for a task cluster."""
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(seconds=default_ttl_seconds)
        records = supporting_records or []
        evidence_ids = cluster.supporting_evidence_ids or [r.record_id for r in records]

        source_types: Set[SourceType] = {r.source_type for r in records if not r.is_tombstone}
        if not source_types:
            source_types = {SourceType.OS_WINDOW}

        candidates: List[Hypothesis] = []

        # Rule 1: Pull Request Review / Bug Fixing
        if any("pull" in app_or_uri.lower() or "pr" in app_or_uri.lower() for app_or_uri in cluster.associated_uris):
            base_prior = 0.90
            conf = self.uncertainty_engine.calibrate_confidence(
                base_prior=base_prior,
                evidence_count=len(evidence_ids),
                source_types=source_types,
            )
            candidates.append(
                Hypothesis(
                    hypothesis_id=generate_uuidv7(),
                    proposed_intent=f"Reviewing or resolving GitHub Pull Request in {cluster.primary_topic or cluster.title}",
                    confidence_score=conf,
                    candidate_evidence_ids=evidence_ids,
                    uncertainty_reasons=["Inferred from browser GitHub pull request URI patterns"],
                    expires_at=expires_at,
                    is_hypothesis=True,
                )
            )

        # Rule 2: Active Coding / Test Debugging
        terminal_keywords = ("terminal", "pty", "powershell", "pwsh", "bash", "zsh", "sh", "cmd")
        has_terminal = any(any(kw in a.lower() for kw in terminal_keywords) for a in cluster.associated_apps)
        has_editor = any("code" in a.lower() or "pycharm" in a.lower() or "cursor" in a.lower() for a in cluster.associated_apps)

        if has_editor and has_terminal:
            base_prior = 0.88
            conf = self.uncertainty_engine.calibrate_confidence(
                base_prior=base_prior,
                evidence_count=len(evidence_ids),
                source_types=source_types,
            )
            candidates.append(
                Hypothesis(
                    hypothesis_id=generate_uuidv7(),
                    proposed_intent=f"Active software development and test execution in {cluster.primary_topic or 'workspace'}",
                    confidence_score=conf,
                    candidate_evidence_ids=evidence_ids,
                    uncertainty_reasons=["Correlated code editor modifications with terminal test runs"],
                    expires_at=expires_at,
                    is_hypothesis=True,
                )
            )
        elif has_editor:
            base_prior = 0.80
            conf = self.uncertainty_engine.calibrate_confidence(
                base_prior=base_prior,
                evidence_count=len(evidence_ids),
                source_types=source_types,
            )
            candidates.append(
                Hypothesis(
                    hypothesis_id=generate_uuidv7(),
                    proposed_intent=f"Source code editing in {cluster.primary_topic or cluster.title}",
                    confidence_score=conf,
                    candidate_evidence_ids=evidence_ids,
                    uncertainty_reasons=["Inferred from IDE window focus"],
                    expires_at=expires_at,
                    is_hypothesis=True,
                )
            )

        # Rule 3: Research / Technical Documentation
        if any("arxiv" in u.lower() or "docs" in u.lower() or "stackoverflow" in u.lower() for u in cluster.associated_uris):
            base_prior = 0.88
            conf = self.uncertainty_engine.calibrate_confidence(
                base_prior=base_prior,
                evidence_count=len(evidence_ids),
                source_types=source_types,
            )
            candidates.append(
                Hypothesis(
                    hypothesis_id=generate_uuidv7(),
                    proposed_intent=f"Technical research and documentation review on {cluster.primary_topic or 'technical topic'}",
                    confidence_score=conf,
                    candidate_evidence_ids=evidence_ids,
                    uncertainty_reasons=["Inferred from documentation/paper reading patterns"],
                    expires_at=expires_at,
                    is_hypothesis=True,
                )
            )

        # Fallback General Hypothesis if no specific rule triggered
        if not candidates:
            base_prior = 0.60
            conf = self.uncertainty_engine.calibrate_confidence(
                base_prior=base_prior,
                evidence_count=len(evidence_ids),
                source_types=source_types,
            )
            candidates.append(
                Hypothesis(
                    hypothesis_id=generate_uuidv7(),
                    proposed_intent=f"General task session in {cluster.primary_app}: {cluster.title}",
                    confidence_score=conf,
                    candidate_evidence_ids=evidence_ids,
                    uncertainty_reasons=["Heuristic fallback based on dominant application window"],
                    expires_at=expires_at,
                    is_hypothesis=True,
                )
            )

        return self.uncertainty_engine.resolve_conflicts(candidates)
