from __future__ import annotations
from abc import ABC, abstractmethod
from typing import List, Optional
from reflex.schemas.memory import TransitionTuple, MotorSkill


class MemoryPortError(Exception):
    """Base exception for MemoryPort operations."""
    pass


class MemoryConnectionError(MemoryPortError):
    """Raised when memory backend connection fails or is disconnected."""
    pass


class MemoryLockError(MemoryPortError):
    """Raised when memory backend encounters lock contention or busy state."""
    pass


class MemoryOutageError(MemoryPortError):
    """Raised when memory store suffers an outage or fatal storage failure."""
    pass


class MemoryReadOnlyError(MemoryPortError):
    """Raised when write operation is attempted on a read-only memory store."""
    pass


class MemoryPort(ABC):
    """Abstract port for persisting episodes and querying compiled skills (Trace / Local SQLite)."""

    @abstractmethod
    async def record_transition(self, transition: TransitionTuple) -> None:
        """Persists a verified transition tuple to storage."""
        ...

    @abstractmethod
    async def get_episode_transitions(self, episode_id: str) -> List[TransitionTuple]:
        """Retrieves chronological transitions for a given episode."""
        ...

    @abstractmethod
    async def find_transitions_by_state(self, state_hash: str) -> List[TransitionTuple]:
        """Retrieves historical transitions originating from a specific UI state hash."""
        ...

    async def get_skill(self, skill_id: str) -> Optional[MotorSkill]:
        """Retrieves a compiled motor skill by ID if supported."""
        return None

    async def record_skill(self, skill: MotorSkill) -> None:
        """Records a compiled motor skill if supported."""
        pass

    async def save_skill(self, skill: MotorSkill) -> None:
        """Saves a compiled motor skill (alias for record_skill)."""
        await self.record_skill(skill)

    async def find_skills_by_preconditions(self, preconditions_hash: str) -> List[MotorSkill]:
        """Retrieves skills matching preconditions hash."""
        return []

    async def list_skills(self) -> List[MotorSkill]:
        """Lists all motor skills."""
        return []

    async def close(self) -> None:
        """Closes memory store connections."""
        pass
