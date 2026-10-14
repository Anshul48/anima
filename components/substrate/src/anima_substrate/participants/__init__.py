# Copyright 2026 Anshul48
# SPDX-License-Identifier: Apache-2.0
"""Pinned participant contract + registry (family contract v1).

A participant family is everything a world needs to do one KIND of
task work: its advertised capabilities/representations, its grant
shape, and four operations — create (advertise), run, recover, change
(upgrade). Families are added by adding a module that registers
itself; the host is never edited for a new family.

Contract v1 (frozen rules):
  C1. Every family operation takes an explicit state dir chosen by the
      caller and writes nothing outside it.
  C2. Capabilities are advertised at world creation and never change
      afterwards; a version upgrade births a successor world with
      lineage back to the old one (the old pins keep verifying).
  C3. run() reports measured cost (ledger consumes) and never claims
      generality beyond the task it ran.
  C4. recover() never invents state: it replays, adopts, or reports.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

FAMILY_CONTRACT_VERSION = "v1"

_REGISTRY: dict[tuple[str, str], "ParticipantFamily"] = {}


class ParticipantFamily(ABC):
    """One participant family at one version. See module docstring."""

    name: str = ""
    version: str = ""

    @property
    @abstractmethod
    def caps(self) -> list[tuple[str, str]]:
        """Advertised capabilities as (name, version) pairs."""

    @property
    @abstractmethod
    def reps(self) -> list[tuple[str, str]]:
        """Advertised representations as (name, version) pairs."""

    @property
    @abstractmethod
    def grant_limits(self) -> dict[str, float]:
        """Fresh-grant limits for worlds of this family."""

    @abstractmethod
    def create(
        self,
        state_dir: str | Path,
        world_id: str,
        params: dict,
        reason: str = "family create",
    ) -> dict:
        """Advertise: birth + activate a world of this family."""

    @abstractmethod
    def run(
        self,
        state_dir: str | Path,
        world_id: str,
        task: dict,
    ) -> dict:
        """Run one task through the world's capabilities."""

    @abstractmethod
    def recover(
        self,
        state_dir: str | Path,
        world_id: str,
    ) -> dict:
        """Recover: reopen-verify + adopt/report, inventing nothing."""

    @abstractmethod
    def change(
        self,
        state_dir: str | Path,
        world_id: str,
        to_version: str,
        reason: str,
    ) -> dict:
        """Upgrade: birth a successor world at to_version with lineage."""


def register_family(family: ParticipantFamily) -> ParticipantFamily:
    """Register a family version; duplicate registration is refused."""
    key = (family.name, family.version)
    if not key[0] or not key[1]:
        raise ValueError("family name and version must both be non-empty")
    if key in _REGISTRY:
        raise ValueError(f"family {key[0]}@{key[1]} is already registered")
    _REGISTRY[key] = family
    return family


def registered(name: str, version: str) -> bool:
    """True when the family version is already registered."""
    return (name, version) in _REGISTRY


def get_family(name: str, version: str) -> ParticipantFamily:
    """Fetch a registered family, or refuse naming what IS registered."""
    try:
        return _REGISTRY[(name, version)]
    except KeyError:
        known = sorted(f"{n}@{v}" for n, v in _REGISTRY)
        raise ValueError(
            f"unknown family {name}@{version}; registered: {known}"
        ) from None


def list_families() -> list[dict[str, str]]:
    """Registered families as [{name, version, contract}] sorted."""
    return [
        {
            "name": n,
            "version": v,
            "contract": FAMILY_CONTRACT_VERSION,
        }
        for n, v in sorted(_REGISTRY)
    ]
