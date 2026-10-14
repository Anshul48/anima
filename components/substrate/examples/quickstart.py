# Copyright 2026 Anshul48
# SPDX-License-Identifier: Apache-2.0
"""anima-substrate quickstart (runs against the INSTALLED package).

Builds a tiny release tree + pins manifest, drives the M1 journey
(init → family-create → family-run → relate → close/reopen
byte-verify → settle), and prints each step. State goes to a fresh
temp dir; nothing is written elsewhere.

Usage:
    pip install anima-substrate   # or: pip install -e .  (checkout)
    python examples/quickstart.py
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import tempfile


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    from anima_substrate.host import api
    from anima_substrate.participants import get_family

    work = Path(tempfile.mkdtemp(prefix="anima-quickstart-"))
    print(f"[1/7] work dir: {work}")

    tree = work / "release"
    pins = {}
    for rel, body in (("app.py", "print('hello')\n"), ("data/seed.txt", "seed-1\n")):
        dest = tree / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(body.encode())
        pins[rel] = sha(body.encode())
    manifest = work / "pins.json"
    manifest.write_text(
        json.dumps(
            {"manifest_version": 1, "release": "demo-1.0", "files": pins},
            indent=2,
            sort_keys=True,
        )
    )
    print(f"[2/7] release tree: {len(pins)} files pinned")

    state = work / "state"
    api.init_run(state)
    print(f"[3/7] run root initialized: {state}")

    fam = get_family("relcheck", "v1")
    fam.create(state, "RC1", {}, "quickstart")
    rep = fam.run(
        state,
        "RC1",
        {"task_id": "Q-T1", "manifest_path": str(manifest), "tree_root": str(tree)},
    )
    print(
        f"[4/7] relcheck run: valid={rep['valid']} "
        f"checked={rep['identity']['checked']} "
        f"cost={rep['measured_cost']}"
    )
    assert rep["valid"]

    api.relate_op(state, "demo-rel", "v1", ["RC1", "SC-L"], "quickstart relationship")
    before = api.org_snapshot_bytes(state)
    del rep
    after = api.org_snapshot_bytes(state)  # close + reopen
    assert before == after, "org state must survive reopen byte-identical"
    print("[5/7] close/reopen: org snapshot byte-identical")

    rec = fam.recover(state, "RC1")
    assert rec["lifecycle"] == "active"
    assert rec["conservation"]["ok"]
    print("[6/7] recover: active, conservation ok")

    fin = api.settle_op(state, ["RC1", "SC-L", "SC-S"], reason="quickstart")
    for wid, hold in fin["stranded"].items():
        assert hold == {"max_cost_usd": 0.0, "max_time_s": 0.0, "max_invocations": 0}, (
            wid
        )
    print(f"[7/7] settle: {fin['settled_terminals']} stranded=0")
    print(f"quickstart OK (state kept at {state})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
