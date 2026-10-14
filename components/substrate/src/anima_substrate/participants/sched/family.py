# Copyright 2026 Anshul48
# SPDX-License-Identifier: Apache-2.0
"""Sched toy participant family behind the pinned contract (v1).

The sched task class (4-5 tasks / 4-5 slots, one deterministic
solver) as a `ParticipantFamily`: birth a world with sched
capabilities, run the single-world work plan through it, recover by
reopen-verify, refuse version changes (only v1 exists). Added
without any host edit: it uses only the public host surface
(`api.open_run`, `api.birth_world`, `api.j1_work_op`) plus public
cap/grant constants.
"""

from __future__ import annotations

from pathlib import Path

from anima_substrate.host import api
from anima_substrate.participants import (
    ParticipantFamily,
    register_family,
    registered,
)


def _caps_for(preset: str) -> tuple[list, list, dict]:
    from anima_substrate.host import pipeline, routing

    presets = {
        "L": (pipeline.L_CAPS, pipeline.L_REPS),
        "S": (pipeline.S_CAPS, pipeline.S_REPS),
        "FUSED": (
            pipeline.FUSED_CAPS,
            [("sched-list", "v2"), ("sched-slot", "v2")],
        ),
        "Q": (
            pipeline.Q_CAPS,
            [("sched-list", "v1")],
        ),
    }
    if preset not in presets:
        raise ValueError(
            f"unknown sched preset {preset!r} (want one of {sorted(presets)}); "
            f"fix: pass params={{'preset': 'L'}}"
        )
    caps, reps = presets[preset]
    return list(caps), list(reps), dict(routing.GRANT_LIMITS)


class SchedFamily(ParticipantFamily):
    """The sched toy task class as a pinned participant family."""

    name = "sched"
    version = "v1"

    @property
    def caps(self) -> list[tuple[str, str]]:
        caps, _, _ = _caps_for("L")
        return caps

    @property
    def reps(self) -> list[tuple[str, str]]:
        _, reps, _ = _caps_for("L")
        return reps

    @property
    def grant_limits(self) -> dict[str, float]:
        _, _, limits = _caps_for("L")
        return limits

    def create(
        self,
        state_dir: str | Path,
        world_id: str,
        params: dict,
        reason: str = "family create",
    ) -> dict:
        """Advertise: birth + fund + activate a sched world."""
        preset = params.get("preset", "L")
        caps, reps, limits = _caps_for(preset)
        rep = api.birth_world(state_dir, world_id, caps, reps, limits, reason)
        rep["family"] = self.name
        rep["family_version"] = self.version
        rep["preset"] = preset
        return rep

    def run(
        self,
        state_dir: str | Path,
        world_id: str,
        task: dict,
    ) -> dict:
        """Run one sched task through the world; report measured cost."""
        task_id = task.get("task_id", f"{world_id}-T1")
        verifier = task.get("verifier")
        host, _ = api.open_run(state_dir)
        if world_id not in host.worlds:
            raise ValueError(
                f"sched run refused: unknown world {world_id!r}; fix: "
                f"create it first via sched@v1 create"
            )
        before = dict(host.consumed.get(world_id, {}))
        rep = api.j1_work_op(state_dir, world_id, task_id, verifier=verifier)
        host, _ = api.open_run(state_dir)
        after = dict(host.consumed.get(world_id, {}))
        rep["measured_cost"] = {
            k: round(after.get(k, 0.0) - before.get(k, 0.0), 6)
            for k in ("max_cost_usd", "max_time_s", "max_invocations")
        }
        return rep

    def recover(
        self,
        state_dir: str | Path,
        world_id: str,
    ) -> dict:
        """Recover: reopen-verify + adopt/report, inventing nothing."""
        host, _ = api.open_run(state_dir)
        if world_id not in host.worlds:
            raise ValueError(f"sched recover refused: unknown world {world_id!r}")
        rec = host.worlds[world_id]
        vdir = Path(rec.instance_state_dir) / "verdicts"
        try:
            conservation = host.verify_conservation()
        except Exception as exc:  # read-only probe: report, don't raise
            conservation = {
                "ok": False,
                "error": f"{type(exc).__name__}: {exc}",
            }
        return {
            "world_id": world_id,
            "lifecycle": rec.lifecycle,
            "conservation": conservation,
            "verdicts": sorted(p.name for p in vdir.glob("verdict-*.json"))
            if vdir.exists()
            else [],
            "holdings": dict(host.holdings.get(world_id, {})),
            "consumed": dict(host.consumed.get(world_id, {})),
        }

    def change(
        self,
        state_dir: str | Path,
        world_id: str,
        to_version: str,
        reason: str,
    ) -> dict:
        """Refuse: sched ships one version (v1); nothing to upgrade to."""
        raise ValueError(
            f"sched change refused: {world_id} is sched@v1 and the only "
            f"registered sched version is v1 (asked {to_version!r}); no "
            f"successor exists — fix: keep v1 or add a sched v2 family"
        )


if not registered(SchedFamily.name, SchedFamily.version):
    register_family(SchedFamily())
