"""Reflex Cognition Skills Module: System-2 to System-1 Skill Consolidation Lifecycle.

Exposes:
- SkillExtractor: Mines golden episodes, parameterizes slots, and hashes DOM subgraphs.
- ShadowValidator: Background shadow evaluation alongside System 2 without dispatching to host.
- SkillRegistry: In-memory & SQLite skill storage, sub-5ms matching, lifecycle management.
- SkillReplayExecutor: Parameterized instantiation with mandatory live dynamic re-grounding.
"""

from reflex.cognition.skills.executor import (
    SkillExecutionResult,
    SkillExecutionStepResult,
    SkillGroundingError,
    SkillReplayExecutor,
)
from reflex.cognition.skills.extractor import (
    AffordanceItem,
    AffordancePattern,
    SkillExtractor,
)
from reflex.cognition.skills.registry import (
    SkillMatchResult,
    SkillMetadata,
    SkillRegistry,
    SkillRegistryPort,
    SkillStatus,
)
from reflex.cognition.skills.shadow_validator import (
    ShadowRunReport,
    ShadowStepEvaluation,
    ShadowValidator,
)

__all__ = [
    "SkillExtractor",
    "AffordanceItem",
    "AffordancePattern",
    "ShadowValidator",
    "ShadowStepEvaluation",
    "ShadowRunReport",
    "SkillRegistry",
    "SkillRegistryPort",
    "SkillMetadata",
    "SkillStatus",
    "SkillMatchResult",
    "SkillReplayExecutor",
    "SkillExecutionResult",
    "SkillExecutionStepResult",
    "SkillGroundingError",
]
