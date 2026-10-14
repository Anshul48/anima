"""Reflex Surprise Evaluator: Multimodal prediction error estimation and cause attribution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Set, Tuple

from reflex.ports.prediction import PredictionEvaluation, SurpriseEvaluatorPort
from reflex.schemas.actions import ActionType, TypedAction
from reflex.schemas.delta import OutcomeClass, StateDelta
from reflex.schemas.state import CanonicalUIGraph, NodeRole


@dataclass(frozen=True)
class SurpriseEvaluatorConfig:
    """Configuration for SurpriseEvaluator weights and tolerances."""
    weight_structural: float = 0.50
    weight_text: float = 0.30
    weight_visual: float = 0.20
    default_threshold: float = 0.25
    benign_pixel_ratio_tolerance: float = 0.03


class SurpriseEvaluator(SurpriseEvaluatorPort):
    """Evaluates prediction error (Surprise PE) between expected ΔS_hat and observed ΔS.

    Combines structural graph difference, text content mismatch, and visual change ratio
    into a normalized prediction error score PE in [0.0, 1.0].
    Attributing specific inferred diagnostic causes when PE exceeds calibrated thresholds.
    """

    ERROR_TEXT_INDICATORS = (
        "404",
        "500",
        "not found",
        "error",
        "exception",
        "fatal",
        "access denied",
        "forbidden",
        "invalid",
        "failed to load",
        "page not found",
        "unhandled",
        "crashed",
    )

    def __init__(self, config: Optional[SurpriseEvaluatorConfig] = None) -> None:
        self.config = config or SurpriseEvaluatorConfig()

    def evaluate_surprise(
        self,
        expected_delta: StateDelta,
        observed_delta: StateDelta,
        threshold: Optional[float] = None,
        before_state: Optional[CanonicalUIGraph] = None,
        after_state: Optional[CanonicalUIGraph] = None,
        action: Optional[TypedAction] = None,
    ) -> PredictionEvaluation:
        """Computes normalized prediction error PE in [0.0, 1.0] and attributes cause."""
        effective_threshold = threshold if threshold is not None else self.config.default_threshold

        d_struct = self.compute_structural_mismatch(expected_delta, observed_delta)
        d_text = self.compute_text_mismatch(
            expected_delta,
            observed_delta,
            before_state=before_state,
            after_state=after_state,
            action=action,
        )
        d_vis = self.compute_visual_mismatch(expected_delta, observed_delta)

        # Weighted composite prediction error
        pe_raw = (
            self.config.weight_structural * d_struct
            + self.config.weight_text * d_text
            + self.config.weight_visual * d_vis
        )
        pe = round(max(0.0, min(1.0, pe_raw)), 4)
        is_surprised = pe > effective_threshold

        inferred_cause = self.infer_cause(
            expected=expected_delta,
            observed=observed_delta,
            pe=pe,
            threshold=effective_threshold,
            d_struct=d_struct,
            d_text=d_text,
            d_vis=d_vis,
            after_state=after_state,
        )

        return PredictionEvaluation(
            prediction_error=pe,
            surprise_threshold=effective_threshold,
            is_surprised=is_surprised,
            structural_mismatch=round(d_struct, 4),
            text_mismatch=round(d_text, 4),
            visual_mismatch=round(d_vis, 4),
            inferred_cause=inferred_cause,
        )

    def compute_structural_mismatch(
        self,
        expected: StateDelta,
        observed: StateDelta,
    ) -> float:
        """Computes normalized structural graph distance d_struct in [0.0, 1.0]."""
        # 1. Outcome class mismatch penalty
        exp_out = expected.outcome_class
        obs_out = observed.outcome_class

        if exp_out == obs_out:
            outcome_penalty = 0.0
        elif obs_out == OutcomeClass.ERROR:
            outcome_penalty = 1.0
        elif obs_out == OutcomeClass.MODAL_APPEARED and exp_out != OutcomeClass.MODAL_APPEARED:
            outcome_penalty = 0.95
        elif obs_out == OutcomeClass.NOOP and exp_out != OutcomeClass.NOOP:
            outcome_penalty = 0.90
        elif obs_out == OutcomeClass.UNKNOWN_EFFECT:
            outcome_penalty = 0.85
        elif exp_out == OutcomeClass.NAVIGATION and obs_out != OutcomeClass.NAVIGATION:
            outcome_penalty = 0.85
        elif obs_out == OutcomeClass.NAVIGATION and exp_out != OutcomeClass.NAVIGATION:
            outcome_penalty = 0.80
        elif exp_out == OutcomeClass.SUCCESS and obs_out == OutcomeClass.LOADING:
            outcome_penalty = 0.10  # Benign loading latency
        elif exp_out == OutcomeClass.LOADING and obs_out == OutcomeClass.SUCCESS:
            outcome_penalty = 0.05
        else:
            outcome_penalty = 0.70

        # 2. Node set Jaccard distances
        def set_jaccard_dist(s1: Set[str], s2: Set[str]) -> float:
            if not s1 and not s2:
                return 0.0
            union = s1 | s2
            if not union:
                return 0.0
            intersection = s1 & s2
            return 1.0 - (len(intersection) / len(union))

        d_added = set_jaccard_dist(set(expected.added_nodes), set(observed.added_nodes))
        d_removed = set_jaccard_dist(set(expected.removed_nodes), set(observed.removed_nodes))
        d_modified = set_jaccard_dist(set(expected.modified_nodes), set(observed.modified_nodes))

        # Average active node set differences
        active_diffs = []
        if expected.added_nodes or observed.added_nodes:
            active_diffs.append(d_added)
        if expected.removed_nodes or observed.removed_nodes:
            active_diffs.append(d_removed)
        if expected.modified_nodes or observed.modified_nodes:
            active_diffs.append(d_modified)

        nodes_dist = sum(active_diffs) / len(active_diffs) if active_diffs else 0.0

        if exp_out == obs_out and nodes_dist == 0.0:
            return 0.0

        # Blend node set difference with outcome class compatibility
        return min(1.0, 0.40 * nodes_dist + 0.60 * outcome_penalty)

    def compute_text_mismatch(
        self,
        expected: StateDelta,
        observed: StateDelta,
        before_state: Optional[CanonicalUIGraph] = None,
        after_state: Optional[CanonicalUIGraph] = None,
        action: Optional[TypedAction] = None,
    ) -> float:
        """Computes text and value mismatch d_text in [0.0, 1.0]."""
        obs_out = observed.outcome_class
        exp_out = expected.outcome_class

        # Check for explicit error text in after_state nodes if available
        if after_state and after_state.nodes:
            for n in after_state.nodes.values():
                n_text = f"{n.label} {n.value}".lower()
                if any(err_kw in n_text for err_kw in self.ERROR_TEXT_INDICATORS):
                    if obs_out in (OutcomeClass.ERROR, OutcomeClass.MODAL_APPEARED) or exp_out == OutcomeClass.SUCCESS:
                        return 1.0

        # Check action typing verification if after_state is present
        if action and action.action_type == ActionType.TYPE and action.text_payload is not None:
            target_id = action.target_node_id
            if after_state and target_id and target_id in after_state.nodes:
                actual_val = after_state.nodes[target_id].value
                if actual_val == action.text_payload:
                    return 0.0
                elif action.text_payload in actual_val:
                    return 0.10
                else:
                    return self._levenshtein_distance_ratio(action.text_payload, actual_val)

        # Heuristic fallback based on outcome class and delta
        if obs_out == OutcomeClass.ERROR:
            return 1.0
        elif obs_out == OutcomeClass.MODAL_APPEARED and exp_out != OutcomeClass.MODAL_APPEARED:
            return 0.80
        elif obs_out == OutcomeClass.NOOP and exp_out != OutcomeClass.NOOP and expected.modified_nodes:
            return 0.80
        elif obs_out == exp_out:
            return 0.0

        return 0.0

    def compute_visual_mismatch(
        self,
        expected: StateDelta,
        observed: StateDelta,
    ) -> float:
        """Computes visual difference d_vis in [0.0, 1.0]."""
        exp_ratio = float(expected.pixel_change_ratio)
        obs_ratio = float(observed.pixel_change_ratio)
        delta_ratio = abs(exp_ratio - obs_ratio)

        # Benign noise filtering: minor pixel shifts under tolerance are suppressed
        if delta_ratio <= self.config.benign_pixel_ratio_tolerance:
            return delta_ratio * 0.5

        return min(1.0, delta_ratio)

    def infer_cause(
        self,
        expected: StateDelta,
        observed: StateDelta,
        pe: float,
        threshold: float,
        d_struct: float,
        d_text: float,
        d_vis: float,
        after_state: Optional[CanonicalUIGraph] = None,
    ) -> str:
        """Attributes diagnostic cause to the prediction error assessment."""
        obs_out = observed.outcome_class
        exp_out = expected.outcome_class

        if pe <= threshold:
            if d_struct == 0.0 and d_text == 0.0 and d_vis > 0.0:
                return "Benign Noise (Rendering/Cursor)"
            return "Expected Transition"

        # High surprise causes
        if obs_out == OutcomeClass.MODAL_APPEARED or (
            after_state and any(n.role == NodeRole.MODAL for n in after_state.nodes.values())
        ):
            return "Unexpected Modal Interception"

        if obs_out == OutcomeClass.ERROR:
            return "Execution Error / Application Fault"

        if obs_out == OutcomeClass.NOOP and exp_out != OutcomeClass.NOOP:
            return "Dead Click / Unresponsive Element"

        if obs_out == OutcomeClass.UNKNOWN_EFFECT:
            return "Settlement Timeout / Unconfirmed State"

        if exp_out == OutcomeClass.NAVIGATION and obs_out != OutcomeClass.NAVIGATION:
            return "Navigation Failure"

        if obs_out == OutcomeClass.NAVIGATION and exp_out != OutcomeClass.NAVIGATION:
            return "Unexpected Navigation"

        if d_text >= 0.70:
            return "Text / Value Mismatch"

        if d_vis >= 0.70:
            return "Severe Visual Layout Shift"

        if d_struct >= 0.50:
            return "Structural State Mismatch"

        return "Unclassified State Divergence"

    @staticmethod
    def _levenshtein_distance_ratio(s1: str, s2: str) -> float:
        """Normalized Levenshtein edit distance in [0.0, 1.0]."""
        if s1 == s2:
            return 0.0
        if not s1 or not s2:
            return 1.0

        len1, len2 = len(s1), len(s2)
        dp = [[0] * (len2 + 1) for _ in range(len1 + 1)]

        for i in range(len1 + 1):
            dp[i][0] = i
        for j in range(len2 + 1):
            dp[0][j] = j

        for i in range(1, len1 + 1):
            for j in range(1, len2 + 1):
                cost = 0 if s1[i - 1] == s2[j - 1] else 1
                dp[i][j] = min(
                    dp[i - 1][j] + 1,      # deletion
                    dp[i][j - 1] + 1,      # insertion
                    dp[i - 1][j - 1] + cost  # substitution
                )

        dist = dp[len1][len2]
        max_len = max(len1, len2)
        return min(1.0, float(dist) / float(max_len))
