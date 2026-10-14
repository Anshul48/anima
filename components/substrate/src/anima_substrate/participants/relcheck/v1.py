# Copyright 2026 Anshul48
# SPDX-License-Identifier: Apache-2.0
"""relcheck v1 participant family: file-backed release-identity checks."""

from __future__ import annotations

from pathlib import Path

from anima_substrate.host import api
from anima_substrate.participants import (
    ParticipantFamily,
    register_family,
    registered,
)
from anima_substrate.participants.relcheck.runner import (
    GRANT_LIMITS,
    recover_world,
    run_task,
)


class RelcheckV1(ParticipantFamily):
    """Release-identity pins over real files (manifest_version 1)."""

    name = "relcheck"
    version = "v1"

    CAP = "relcheck.verify"
    CAP_VER = "v1"

    @property
    def caps(self) -> list[tuple[str, str]]:
        return [(self.CAP, self.CAP_VER)]

    @property
    def reps(self) -> list[tuple[str, str]]:
        return [("relcheck-pins", "v1")]

    @property
    def grant_limits(self) -> dict[str, float]:
        return dict(GRANT_LIMITS)

    def create(
        self,
        state_dir: str | Path,
        world_id: str,
        params: dict,
        reason: str = "family create",
    ) -> dict:
        """Advertise: birth + fund + activate a relcheck v1 world."""
        rep = api.birth_world(
            state_dir,
            world_id,
            self.caps,
            self.reps,
            self.grant_limits,
            reason,
        )
        rep["family"] = self.name
        rep["family_version"] = self.version
        return rep

    def run(
        self,
        state_dir: str | Path,
        world_id: str,
        task: dict,
    ) -> dict:
        """Run one identity check; report measured cost."""
        return run_task(
            self.name,
            self.version,
            self.CAP,
            self.CAP_VER,
            state_dir,
            world_id,
            task,
        )

    def recover(
        self,
        state_dir: str | Path,
        world_id: str,
    ) -> dict:
        """Recover: reopen-verify + adopt/report, inventing nothing."""
        return recover_world(self.name, state_dir, world_id)

    def change(
        self,
        state_dir: str | Path,
        world_id: str,
        to_version: str,
        reason: str,
    ) -> dict:
        """Upgrade: birth a v2 successor world with lineage (C2).

        Only v1→v2 exists; anything else refuses naming the
        registered relcheck versions. The old world is untouched and
        its pins keep verifying.
        """
        from anima_substrate.participants import get_family

        if to_version != "v2":
            raise ValueError(
                f"relcheck change refused: {world_id} is relcheck@v1, "
                f"upgradable only to v2 (asked {to_version!r}); fix: "
                f"change to 'v2' or keep v1"
            )
        successor = get_family("relcheck", "v2")
        host, _ = api.open_run(state_dir)
        if world_id not in host.worlds:
            raise ValueError(f"relcheck change refused: unknown world {world_id!r}")
        child_id = f"{world_id}-v2"
        if child_id in host.worlds:
            raise ValueError(
                f"relcheck change refused: successor {child_id!r} "
                f"already exists (ids never reused)"
            )
        return successor.create(
            state_dir,
            child_id,
            {"derived_from": world_id, "change_reason": reason},
            reason,
        )


if not registered(RelcheckV1.name, RelcheckV1.version):
    register_family(RelcheckV1())
