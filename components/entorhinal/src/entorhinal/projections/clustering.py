"""Session Clustering Engine and Composite Distance Metric.

Implements:
1. Composite Distance calculation:
   Distance(E_i, E_j) = alpha * CosineDistance(v_i, v_j) + beta * TemporalDistance(t_i, t_j)
2. Sliding-window debouncing and smoothing (<30s transient context switches merged into primary task).
3. Deterministic term frequency vectorization of application metadata, titles, and URIs.
"""

from __future__ import annotations

from datetime import datetime, timezone
import math
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from entorhinal.projections.models import SessionTaskCluster
from entorhinal.schemas.models import EvidenceRecord, generate_uuidv7


# Stopwords for text vectorization
DEFAULT_STOPWORDS: Set[str] = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "has", "he",
    "in", "is", "it", "its", "of", "on", "that", "the", "to", "was", "were",
    "will", "with", "the", "this", "but", "they", "have", "had", "what", "when",
    "where", "who", "which", "why", "how", "all", "any", "both", "each", "few",
    "more", "most", "other", "some", "such", "no", "nor", "not", "only", "own",
    "same", "so", "than", "too", "very", "s", "t", "can", "will", "just", "don",
    "should", "now", "http", "https", "com", "org", "net", "io", "html", "php"
}


class SessionClusterEngine:
    """Clustering engine grouping discrete evidence events into cohesive task sessions."""

    def __init__(
        self,
        alpha: float = 0.65,
        beta: float = 0.35,
        max_temporal_gap_seconds: float = 1800.0,
        transient_threshold_seconds: float = 30.0,
        cluster_distance_threshold: float = 0.55,
    ) -> None:
        """Initialize cluster engine with calibrated weights."""
        self.alpha = alpha
        self.beta = beta
        self.max_temporal_gap_seconds = max_temporal_gap_seconds
        self.transient_threshold_seconds = transient_threshold_seconds
        self.cluster_distance_threshold = cluster_distance_threshold

    # --------------------------------------------------------------------------
    # Deterministic Feature Vectorization
    # --------------------------------------------------------------------------

    def extract_tokens(self, text: Optional[str]) -> List[str]:
        """Extract clean alphanumeric tokens from arbitrary text."""
        if not text:
            return []
        # Split on non-alphanumeric, camelCase, path separators
        subbed = re.sub(r"([a-z])([A-Z])", r"\1 \2", text)
        words = re.findall(r"[a-zA-Z0-9_-]{2,}", subbed.lower())
        return [w for w in words if w not in DEFAULT_STOPWORDS and not w.isdigit()]

    def extract_features(self, record: EvidenceRecord) -> Dict[str, float]:
        """Extract normalized term-frequency vector from an EvidenceRecord."""
        tokens: List[str] = []

        # App identifier (high weight)
        app_tokens = self.extract_tokens(record.app_identifier)
        for t in app_tokens:
            tokens.extend([f"app:{t}"] * 3)

        # Window title
        if record.window_title:
            title_tokens = self.extract_tokens(record.window_title)
            tokens.extend(title_tokens)

        # Target URI
        if record.target_uri:
            uri_tokens = self.extract_tokens(record.target_uri)
            for t in uri_tokens:
                tokens.extend([f"uri:{t}"] * 2)

        # Payload strings
        if record.sanitized_payload:
            for k, v in record.sanitized_payload.items():
                if isinstance(v, str):
                    tokens.extend(self.extract_tokens(v))
                elif isinstance(v, list):
                    for item in v:
                        if isinstance(item, str):
                            tokens.extend(self.extract_tokens(item))

        # Compute raw term frequency
        tf: Dict[str, float] = {}
        for tok in tokens:
            tf[tok] = tf.get(tok, 0.0) + 1.0

        # L2-normalize the vector
        if not tf:
            return {}

        norm = math.sqrt(sum(val * val for val in tf.values()))
        if norm > 0.0:
            return {k: v / norm for k, v in tf.items()}
        return tf

    # --------------------------------------------------------------------------
    # Distance Calculations
    # --------------------------------------------------------------------------

    def compute_cosine_distance(self, vec_a: Dict[str, float], vec_b: Dict[str, float]) -> float:
        """Compute Cosine Distance between two sparse term vectors (1.0 - cosine_sim)."""
        if not vec_a and not vec_b:
            return 0.0
        if not vec_a or not vec_b:
            return 1.0

        # Compute dot product between sparse representations
        dot_product = 0.0
        # Iterate over smaller dictionary
        smaller, larger = (vec_a, vec_b) if len(vec_a) <= len(vec_b) else (vec_b, vec_a)
        for term, val in smaller.items():
            if term in larger:
                dot_product += val * larger[term]

        similarity = max(0.0, min(1.0, dot_product))
        return 1.0 - similarity

    def compute_temporal_distance(self, t_a: datetime, t_b: datetime) -> float:
        """Compute normalized temporal distance bounded in [0.0, 1.0]."""
        delta_seconds = abs((t_a - t_b).total_seconds())
        return min(1.0, delta_seconds / self.max_temporal_gap_seconds)

    def compute_composite_distance(self, record_a: EvidenceRecord, record_b: EvidenceRecord) -> float:
        """Compute the weighted composite distance between two EvidenceRecords."""
        vec_a = self.extract_features(record_a)
        vec_b = self.extract_features(record_b)

        cos_dist = self.compute_cosine_distance(vec_a, vec_b)
        temp_dist = self.compute_temporal_distance(record_a.persisted_at, record_b.persisted_at)

        return (self.alpha * cos_dist) + (self.beta * temp_dist)

    def compute_distance_to_cluster(
        self,
        cluster: SessionTaskCluster,
        record: EvidenceRecord,
    ) -> float:
        """Compute composite distance between a cluster centroid and a new record."""
        rec_vec = self.extract_features(record)
        cos_dist = self.compute_cosine_distance(cluster.centroid_terms, rec_vec)
        temp_dist = self.compute_temporal_distance(cluster.end_time, record.persisted_at)

        return (self.alpha * cos_dist) + (self.beta * temp_dist)

    # --------------------------------------------------------------------------
    # Incremental Active Cluster Update
    # --------------------------------------------------------------------------

    def update_active_cluster(
        self,
        current_cluster: Optional[SessionTaskCluster],
        record: EvidenceRecord,
        distance_threshold: Optional[float] = None,
    ) -> Tuple[SessionTaskCluster, bool]:
        """Incorporate a new record into current cluster or start a new cluster.

        Returns (updated_or_new_cluster, is_new_cluster_started).
        """
        threshold = distance_threshold or self.cluster_distance_threshold
        rec_vec = self.extract_features(record)

        if current_cluster is None:
            # Initialize brand new cluster
            new_cluster = SessionTaskCluster(
                cluster_id=generate_uuidv7(),
                title=self._generate_cluster_title(record),
                start_time=record.persisted_at,
                end_time=record.persisted_at,
                primary_app=record.app_identifier,
                primary_topic=self._infer_topic(record),
                associated_apps=[record.app_identifier],
                associated_uris=[record.target_uri] if record.target_uri else [],
                event_count=1,
                duration_seconds=0.0,
                supporting_evidence_ids=[record.record_id],
                centroid_terms=rec_vec,
                is_transient=False,
            )
            return new_cluster, True

        # Check distance to current active cluster
        dist = self.compute_distance_to_cluster(current_cluster, record)

        if dist <= threshold:
            # Merge into active cluster
            updated_apps = list(set(current_cluster.associated_apps + [record.app_identifier]))
            updated_uris = list(set(current_cluster.associated_uris + ([record.target_uri] if record.target_uri else [])))
            new_count = current_cluster.event_count + 1
            new_end = max(current_cluster.end_time, record.persisted_at)
            duration = (new_end - current_cluster.start_time).total_seconds()

            # Update centroid terms with running average
            merged_terms = dict(current_cluster.centroid_terms)
            for k, v in rec_vec.items():
                merged_terms[k] = merged_terms.get(k, 0.0) + v
            # Re-normalize centroid
            norm = math.sqrt(sum(v * v for v in merged_terms.values()))
            if norm > 0.0:
                merged_terms = {k: v / norm for k, v in merged_terms.items()}

            updated_cluster = SessionTaskCluster(
                cluster_id=current_cluster.cluster_id,
                title=current_cluster.title,
                start_time=current_cluster.start_time,
                end_time=new_end,
                primary_app=current_cluster.primary_app,
                primary_topic=current_cluster.primary_topic or self._infer_topic(record),
                associated_apps=updated_apps,
                associated_uris=updated_uris,
                event_count=new_count,
                duration_seconds=max(0.0, duration),
                supporting_evidence_ids=current_cluster.supporting_evidence_ids + [record.record_id],
                centroid_terms=merged_terms,
                is_transient=False,
                metadata=current_cluster.metadata,
            )
            return updated_cluster, False

        # Otherwise, start a new cluster
        new_cluster = SessionTaskCluster(
            cluster_id=generate_uuidv7(),
            title=self._generate_cluster_title(record),
            start_time=record.persisted_at,
            end_time=record.persisted_at,
            primary_app=record.app_identifier,
            primary_topic=self._infer_topic(record),
            associated_apps=[record.app_identifier],
            associated_uris=[record.target_uri] if record.target_uri else [],
            event_count=1,
            duration_seconds=0.0,
            supporting_evidence_ids=[record.record_id],
            centroid_terms=rec_vec,
            is_transient=False,
        )
        return new_cluster, True

    # --------------------------------------------------------------------------
    # Batch Clustering & Sliding-Window Smoothing
    # --------------------------------------------------------------------------

    def cluster_records(
        self,
        records: List[EvidenceRecord],
        distance_threshold: Optional[float] = None,
    ) -> List[SessionTaskCluster]:
        """Cluster a sequential list of EvidenceRecords into discrete session clusters."""
        if not records:
            return []

        threshold = distance_threshold or self.cluster_distance_threshold
        sorted_records = sorted(records, key=lambda r: r.persisted_at)

        clusters: List[SessionTaskCluster] = []
        active_cluster: Optional[SessionTaskCluster] = None

        for rec in sorted_records:
            if rec.is_tombstone:
                continue

            if active_cluster is None:
                active_cluster, _ = self.update_active_cluster(None, rec, threshold)
            else:
                updated, is_new = self.update_active_cluster(active_cluster, rec, threshold)
                if is_new:
                    clusters.append(active_cluster)
                    active_cluster = updated
                else:
                    active_cluster = updated

        if active_cluster is not None:
            clusters.append(active_cluster)

        # Apply sliding-window smoothing for transient interruptions
        return self.smooth_clusters(clusters, self.transient_threshold_seconds)

    def smooth_clusters(
        self,
        clusters: List[SessionTaskCluster],
        transient_threshold_seconds: float = 30.0,
    ) -> List[SessionTaskCluster]:
        """Merge short transient interruptions (<30s) back into the surrounding primary task session."""
        if len(clusters) <= 1:
            return clusters

        smoothed: List[SessionTaskCluster] = []
        i = 0

        while i < len(clusters):
            curr = clusters[i]

            # Check if current cluster is a short transient switch sandwiched between related clusters
            is_short = curr.duration_seconds < transient_threshold_seconds or curr.event_count <= 2

            if is_short and smoothed and (i + 1 < len(clusters)):
                prev = smoothed[-1]
                next_c = clusters[i + 1]

                # If previous and next share the same primary app/topic or close distance
                vec_prev = prev.centroid_terms
                vec_next = next_c.centroid_terms
                cos_dist = self.compute_cosine_distance(vec_prev, vec_next)

                if cos_dist < 0.40 or prev.primary_app == next_c.primary_app:
                    # Absorb both transient curr and resuming next_c into prev
                    merged_apps = list(set(prev.associated_apps + curr.associated_apps + next_c.associated_apps))
                    merged_uris = list(set(prev.associated_uris + curr.associated_uris + next_c.associated_uris))
                    merged_evidence = prev.supporting_evidence_ids + curr.supporting_evidence_ids + next_c.supporting_evidence_ids
                    new_end = max(prev.end_time, curr.end_time, next_c.end_time)
                    new_duration = (new_end - prev.start_time).total_seconds()

                    smoothed[-1] = SessionTaskCluster(
                        cluster_id=prev.cluster_id,
                        title=prev.title,
                        start_time=prev.start_time,
                        end_time=new_end,
                        primary_app=prev.primary_app,
                        primary_topic=prev.primary_topic,
                        associated_apps=merged_apps,
                        associated_uris=merged_uris,
                        event_count=prev.event_count + curr.event_count + next_c.event_count,
                        duration_seconds=max(0.0, new_duration),
                        supporting_evidence_ids=merged_evidence,
                        centroid_terms=prev.centroid_terms,
                        is_transient=False,
                        metadata=prev.metadata,
                    )
                    i += 2
                    continue

            smoothed.append(curr)
            i += 1

        return smoothed

    # --------------------------------------------------------------------------
    # Helper Inferences
    # --------------------------------------------------------------------------

    def _generate_cluster_title(self, record: EvidenceRecord) -> str:
        """Generate a human-readable title for a task cluster."""
        if record.window_title:
            clean = record.window_title.strip()
            if len(clean) > 60:
                return clean[:57] + "..."
            return clean
        if record.target_uri:
            return f"Activity in {record.target_uri}"
        return f"{record.app_identifier} Session"

    def _infer_topic(self, record: EvidenceRecord) -> str:
        """Extract primary topic or repository name from EvidenceRecord."""
        if record.target_uri:
            # Check github repo pattern
            match = re.search(r"github\.com/([^/]+/[^/#?]+)", record.target_uri)
            if match:
                return match.group(1)
            # Check file path
            return record.target_uri.split("/")[-1]
        if record.window_title:
            words = record.window_title.split(" - ")
            if len(words) > 1:
                return words[0]
        return record.app_identifier
