# Copyright 2026 Anshul48
# SPDX-License-Identifier: Apache-2.0
"""Minimal external participant family (copy-and-adapt template).

Shows how to add your own world kind through the published family
contract WITHOUT editing the host: subclass ParticipantFamily,
implement create/run/recover/change with the public host surface
only (api.init_run / birth_world / open_run), register it, and drive
it. Runs against the INSTALLED package; state goes to a fresh temp
dir; nothing is written elsewhere.

Usage:
    pip install <wheel-from-release>   # or: pip install -e . (checkout)
    python examples/external_participant.py
"""

from __future__ import annotations

from pathlib import Path
import tempfile


def main() -> int:
    from anima_substrate.host import api
    from anima_substrate.participants import (
        ParticipantFamily,
        get_family,
        list_families,
        register_family,
        registered,
    )

    class WordcountFamily(ParticipantFamily):
        """Count words: the smallest honest participant family."""

        name = "wordcount"
        version = "v1"

        @property
        def caps(self) -> list[tuple[str, str]]:
            return [("wordcount", "v1")]

        @property
        def reps(self) -> list[tuple[str, str]]:
            return [("wordcount-text", "v1")]

        @property
        def grant_limits(self) -> dict[str, float]:
            return {"max_cost_usd": 1.0, "max_time_s": 60.0, "max_invocations": 100}

        def create(self, state_dir, world_id, params, reason="family create"):
            rep = api.birth_world(
                state_dir, world_id, self.caps, self.reps, self.grant_limits, reason
            )
            rep["family"] = self.name
            rep["family_version"] = self.version
            return rep

        def run(self, state_dir, world_id, task):
            host, _ = api.open_run(state_dir)
            if world_id not in host.worlds:
                raise ValueError(
                    f"wordcount run refused: unknown world {world_id!r}; "
                    "fix: create it first via wordcount@v1 create"
                )
            text = task.get("text")
            if not isinstance(text, str) or not text:
                raise ValueError(
                    "wordcount run refused: task needs non-empty 'text'; "
                    "fix: pass {'text': '...'}"
                )
            before = dict(host.consumed.get(world_id, {}))
            count = len(text.split())
            host, _ = api.open_run(state_dir)
            after = dict(host.consumed.get(world_id, {}))
            # Measured cost: this family does no ledger-recorded work,
            # so the honest delta is zeros (C3: report measured cost,
            # never claim generality beyond the task run).
            keys = ("max_cost_usd", "max_time_s", "max_invocations")
            return {
                "world_id": world_id,
                "word_count": count,
                "measured_cost": {
                    k: round(after.get(k, 0.0) - before.get(k, 0.0), 6) for k in keys
                },
            }

        def recover(self, state_dir, world_id):
            host, _ = api.open_run(state_dir)
            if world_id not in host.worlds:
                raise ValueError(
                    f"wordcount recover refused: unknown world {world_id!r}"
                )
            try:
                conservation = host.verify_conservation()
            except Exception as exc:  # read-only probe: report, don't raise
                conservation = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
            return {
                "world_id": world_id,
                "lifecycle": host.worlds[world_id].lifecycle,
                "conservation": conservation,
            }

        def change(self, state_dir, world_id, to_version, reason):
            raise ValueError(
                f"wordcount change refused: {world_id} is wordcount@v1, "
                "the only version (asked "
                f"{to_version!r}); fix: keep v1 or add a v2 family module"
            )

    if not registered("wordcount", "v1"):
        register_family(WordcountFamily())
    fam = get_family("wordcount", "v1")
    print(
        f"[1/5] registered: {[f['name'] + '@' + f['version'] for f in list_families() if f['name'] == 'wordcount']}"
    )

    work = Path(tempfile.mkdtemp(prefix="anima-extpart-"))
    state = work / "state"
    api.init_run(state)
    print(f"[2/5] run root initialized: {state}")

    rep = fam.create(state, "WC1", {}, reason="external example")
    print(f"[3/5] world birthed: {rep['world_id']} caps={rep['caps']}")

    out = fam.run(state, "WC1", {"text": "hello accountable worlds"})
    print(f"[4/5] run: word_count={out['word_count']} cost={out['measured_cost']}")
    assert out["word_count"] == 3, out

    rec = fam.recover(state, "WC1")
    print(
        f"[5/5] recover: lifecycle={rec['lifecycle']} conservation_ok={rec['conservation'].get('ok')}"
    )
    assert rec["conservation"].get("ok") is True, rec
    try:
        fam.change(state, "WC1", "v2", reason="demo refusal")
    except ValueError as exc:
        print(f"change refusal (expected): {exc}")
    else:  # pragma: no cover
        raise AssertionError("change to v2 should have refused")
    print("external-participant OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
