"""Reflex: Predictive Computer-Use Agent Schema Package."""

from reflex.schemas.actions import ActionType, NormalizedCoords, SafetyClass, TypedAction
from reflex.schemas.delta import OutcomeClass, StateDelta, SurpriseMetric
from reflex.schemas.fallback import CropPacket, FallbackLevel
from reflex.schemas.memory import MotorSkill, TransitionTuple
from reflex.schemas.state import BoundingBox, CanonicalUIGraph, ModalitySource, NodeRole, UIStateNode

from reflex.episodes import (
    EpisodeJournalPort,
    EpisodeSummary,
    EpisodeReplayRunner,
    LocalEpisodeJournal,
    PrivacyRedactor,
    ReplayReport,
    ReplayStepResult,
)

from reflex.orchestration import (
    BrowserClosedLoopV1,
    BrowserSession,
    BrowserSessionConfig,
    BrowserSessionManager,
    TaskExecutionReport,
    TaskGoal,
    TaskStatus,
)

__all__ = [
    "ActionType",
    "SafetyClass",
    "NormalizedCoords",
    "TypedAction",
    "NodeRole",
    "ModalitySource",
    "BoundingBox",
    "UIStateNode",
    "CanonicalUIGraph",
    "OutcomeClass",
    "StateDelta",
    "SurpriseMetric",
    "TransitionTuple",
    "MotorSkill",
    "FallbackLevel",
    "CropPacket",
    "EpisodeJournalPort",
    "EpisodeSummary",
    "LocalEpisodeJournal",
    "PrivacyRedactor",
    "ReplayStepResult",
    "ReplayReport",
    "EpisodeReplayRunner",
    "BrowserClosedLoopV1",
    "TaskGoal",
    "TaskExecutionReport",
    "TaskStatus",
    "BrowserSession",
    "BrowserSessionConfig",
    "BrowserSessionManager",
]

