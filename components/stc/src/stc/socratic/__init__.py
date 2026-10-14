"""Socratic elicitation and archetype diffing package."""

from stc.socratic.ambiguity import (
    AMBIGUITY_TAU,
    OPPOSING_PATTERNS,
    TAU,
    compute_ambiguity_score,
    compute_contradiction_penalty,
    compute_error_policy_penalty,
    compute_missing_dimension_penalty,
    generate_archetype_diff,
    generate_archetype_diffs,
)
from stc.socratic.decomposer import SocraticDecomposer

__all__ = [
    "AMBIGUITY_TAU",
    "OPPOSING_PATTERNS",
    "TAU",
    "SocraticDecomposer",
    "compute_ambiguity_score",
    "compute_contradiction_penalty",
    "compute_error_policy_penalty",
    "compute_missing_dimension_penalty",
    "generate_archetype_diff",
    "generate_archetype_diffs",
]
