# SPDX-License-Identifier: Apache-2.0
"""ANIMA root quickstart: report component availability, then run a real
substrate journey (init -> relcheck participant -> byte-identical
close/reopen) against the installed packages.

Usage (from the repo root):

    pip install -e . -e components/substrate
    python examples/quickstart.py
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import tempfile


def main() -> int:
    import anima

    print(f"[1/4] anima {anima.__version__} component availability:")
    for alias, available in anima.components().items():
        print(f"      anima.{alias}: {'installed' if available else 'not installed'}")
    if not anima.components()["substrate"]:
        print("substrate is required for the rest: pip install -e components/substrate")
        return 1

    from anima_substrate.host import api
    from anima_substrate.participants import get_family

    work = Path(tempfile.mkdtemp(prefix="anima-root-quickstart-"))
    tree = work / "release"
    pins = {}
    for rel, body in (("app.py", "print('hello')\n"), ("data/seed.txt", "seed-1\n")):
        dest = tree / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(body.encode())
        pins[rel] = hashlib.sha256(body.encode()).hexdigest()
    manifest = work / "pins.json"
    manifest.write_text(json.dumps(
        {"manifest_version": 1, "release": "demo-1.0", "files": pins},
        indent=2, sort_keys=True))
    print(f"[2/4] pinned release tree: {len(pins)} files")

    state = work / "state"
    api.init_run(state)
    fam = get_family("relcheck", "v1")
    fam.create(state, "RC1", {}, "root-quickstart")
    rep = fam.run(state, "RC1", {
        "task_id": "Q-T1", "manifest_path": str(manifest), "tree_root": str(tree)})
    assert rep["valid"], rep
    print(f"[3/4] relcheck participant: valid={rep['valid']} "
          f"checked={rep['identity']['checked']} cost={rep['measured_cost']}")

    before = api.org_snapshot_bytes(state)
    after = api.org_snapshot_bytes(state)
    assert before == after, "org state must survive reopen byte-identical"
    rec = fam.recover(state, "RC1")
    assert rec["lifecycle"] == "active" and rec["conservation"]["ok"]
    print("[4/4] close/reopen byte-identical; recover: active, conservation ok")
    print(f"ANIMA quickstart OK (state kept at {state})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
