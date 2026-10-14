# Copyright 2026 Anshul48
# SPDX-License-Identifier: Apache-2.0
"""SST participant family (optional extra, caller-staged root).

`sst@v1` runs the snapshot-verified TEST search behind the pinned
participant contract. The package carries NO SST bytes and NO
pydantic: every operation probes a caller-staged SST checkout (see
`docs/SST-STAGING.md`) and refuses loudly before any SST import when
unstaged or drifted. Added without any host edit: it uses only the
public host surface (`api.open_run`, `api.birth_world`,
`MiniHost.invoke`, `MiniHost.store_args`).
"""

from __future__ import annotations

import json
from pathlib import Path
import time

from anima_substrate.host import api
from anima_substrate.host.minihost import atomic_write_text
from anima_substrate.participants import (
    ParticipantFamily,
    register_family,
    registered,
)
from anima_substrate.participants.sst.staged import (
    SSTBoundary,
    probe,
    run_sst_test_search,
    verify_snapshot,
)

__all__ = ["SSTBoundary", "SstFamily", "probe", "verify_snapshot"]


class SstFamily(ParticipantFamily):
    """Snapshot-verified SST search as a pinned participant family."""

    name = "sst"
    version = "v1"

    CAP = "sst.search"
    CAP_VER = "v1"

    @property
    def caps(self) -> list[tuple[str, str]]:
        return [(self.CAP, self.CAP_VER)]

    @property
    def reps(self) -> list[tuple[str, str]]:
        return []

    @property
    def grant_limits(self) -> dict[str, float]:
        return {
            "max_cost_usd": 0.0,
            "max_time_s": 300.0,
            "max_invocations": 10.0,
        }

    def _staging_path(self, state_dir: Path, world_id: str) -> Path:
        return state_dir / "state" / world_id / "sst-staging.json"

    def create(
        self,
        state_dir: str | Path,
        world_id: str,
        params: dict,
        reason: str = "family create",
    ) -> dict:
        """Advertise: probe the staged root, then birth the world.

        The probe runs BEFORE any mutation: an unstaged/drifted root
        refuses with zero ledger effect.
        """
        root = Path(state_dir)
        sst_root = params.get("sst_root") or None
        venv_py = params.get("venv_py") or None
        try:
            evidence = probe(sst_root, venv_py)
        except SSTBoundary as exc:
            raise ValueError(f"sst create refused: {exc}") from exc
        rep = api.birth_world(
            root,
            world_id,
            self.caps,
            self.reps,
            self.grant_limits,
            reason,
        )
        staging = {
            "sst_root": evidence["sst_root"],
            "snapshot_src": evidence["snapshot_src"],
            "venv_py": evidence["venv_py"],
            "snapshot_hash": evidence["snapshot_check"]["snapshot_hash"],
            "pydantic_version": evidence["pydantic_version"],
        }
        atomic_write_text(
            self._staging_path(root, world_id),
            json.dumps(staging, indent=2, sort_keys=True) + "\n",
        )
        rep["family"] = self.name
        rep["family_version"] = self.version
        rep["staging"] = staging
        return rep

    def run(
        self,
        state_dir: str | Path,
        world_id: str,
        task: dict,
    ) -> dict:
        """Run one TEST search through the world; report measured cost."""
        root = Path(state_dir)
        host, _ = api.open_run(root)
        if world_id not in host.worlds:
            raise ValueError(
                f"sst run refused: unknown world {world_id!r}; fix: "
                f"create it first via sst@v1 create"
            )
        staging_file = self._staging_path(root, world_id)
        if task.get("sst_root"):
            src = str(Path(task["sst_root"]) / "src")
            venv = task.get("venv_py")
        elif staging_file.exists():
            staging = json.loads(staging_file.read_text(encoding="utf-8"))
            src = staging["snapshot_src"]
            venv = staging["venv_py"]
        else:
            raise ValueError(
                f"sst run refused: no staging for {world_id!r} (neither "
                f"{staging_file} nor task['sst_root']); fix: pass "
                f"sst_root in the task or re-create the world"
            )
        task_id = task.get("task_id", "sst-T1")
        args_ref = host.store_args(
            world_id,
            f"sst-{task_id}",
            {
                "formulation_ref": f"sst:{task_id}",
                "candidate_refs": [],
                "snapshot_src": src,
            },
        )
        rundir = root / "state" / world_id / "sst-leg" / task_id
        t0 = time.time()

        def _search() -> str:
            rep = run_sst_test_search(rundir, src, venv)
            out = rundir / "sst-evidence.json"
            atomic_write_text(out, json.dumps(rep, indent=2, sort_keys=True) + "\n")
            return str(out)

        try:
            entry = host.invoke(
                "host",
                world_id,
                self.CAP,
                self.CAP_VER,
                args_ref,
                _search,
                cost_usd=0.0,
                time_s=0.0,
            )
        except SSTBoundary as exc:
            raise ValueError(f"sst run refused: {exc}") from exc
        elapsed = time.time() - t0
        evidence = json.loads(
            (rundir / "sst-evidence.json").read_text(encoding="utf-8")
        )
        evidence["task_id"] = task_id
        evidence["invoke_seq"] = entry["seq"]
        evidence["invoke_id"] = entry["payload"]["invoke_id"]
        evidence["measured_cost"] = {
            "max_cost_usd": 0.0,
            "max_time_s": round(elapsed, 3),
            "max_invocations": 1.0,
        }
        return evidence

    def recover(
        self,
        state_dir: str | Path,
        world_id: str,
    ) -> dict:
        """Recover: reopen-verify + re-verify the staged snapshot."""
        root = Path(state_dir)
        host, _ = api.open_run(root)
        if world_id not in host.worlds:
            raise ValueError(f"sst recover refused: unknown world {world_id!r}")
        staging_file = self._staging_path(root, world_id)
        if not staging_file.exists():
            raise ValueError(f"sst recover refused: no staging for {world_id!r}")
        staging = json.loads(staging_file.read_text(encoding="utf-8"))
        try:
            checked = verify_snapshot(staging["snapshot_src"])
        except SSTBoundary as exc:
            return {
                "world_id": world_id,
                "snapshot": "DRIFTED",
                "error": str(exc),
            }
        try:
            conservation = host.verify_conservation()
        except Exception as exc:  # read-only probe: report, don't raise
            conservation = {
                "ok": False,
                "error": f"{type(exc).__name__}: {exc}",
            }
        return {
            "world_id": world_id,
            "lifecycle": host.worlds[world_id].lifecycle,
            "snapshot": checked["verdict"],
            "snapshot_hash": checked["snapshot_hash"],
            "conservation": conservation,
        }

    def change(
        self,
        state_dir: str | Path,
        world_id: str,
        to_version: str,
        reason: str,
    ) -> dict:
        """Refuse: sst ships one contract version (v1)."""
        raise ValueError(
            f"sst change refused: {world_id} is sst@v1 and the only "
            f"registered sst version is v1 (asked {to_version!r}); a new "
            f"snapshot pin needs re-qualification first (see "
            f"docs/SST-STAGING.md §upgrade)"
        )


if not registered(SstFamily.name, SstFamily.version):
    register_family(SstFamily())
