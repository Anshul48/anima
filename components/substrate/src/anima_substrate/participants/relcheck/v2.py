# Copyright 2026 Anshul48
# SPDX-License-Identifier: Apache-2.0
"""relcheck v2 participant family: identity + compat-rule checks."""

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


class RelcheckV2(ParticipantFamily):
    """Identity pins + compat rules (manifest_version 1 or 2)."""

    name = "relcheck"
    version = "v2"

    CAP = "relcheck.verify"
    CAP_VER = "v2"

    @property
    def caps(self) -> list[tuple[str, str]]:
        return [(self.CAP, self.CAP_VER)]

    @property
    def reps(self) -> list[tuple[str, str]]:
        return [("relcheck-pins", "v2")]

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
        """Advertise: birth + fund + activate a relcheck v2 world.

        `params` may carry `derived_from` (v1 world id) + `change_reason`
        for an upgrade birth; the lineage is recorded on the world.
        """
        lineage = None
        if params.get("derived_from"):
            lineage = [
                {"rel": "derived_from", "world": params["derived_from"]},
                {
                    "rel": "change",
                    "from": "v1",
                    "to": "v2",
                    "reason": params.get("change_reason", reason),
                },
            ]
        rep = api.birth_world(
            state_dir,
            world_id,
            self.caps,
            self.reps,
            self.grant_limits,
            reason,
            lineage=lineage,
        )
        rep["family"] = self.name
        rep["family_version"] = self.version
        if lineage:
            rep["derived_from"] = params["derived_from"]
        return rep

    def run(
        self,
        state_dir: str | Path,
        world_id: str,
        task: dict,
    ) -> dict:
        """Run one identity+compat check; report measured cost."""
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
        """Refuse: v2 is the newest registered relcheck version."""
        raise ValueError(
            f"relcheck change refused: {world_id} is already "
            f"relcheck@v2, the newest registered version (asked "
            f"{to_version!r}); no successor exists"
        )


if not registered(RelcheckV2.name, RelcheckV2.version):
    register_family(RelcheckV2())
