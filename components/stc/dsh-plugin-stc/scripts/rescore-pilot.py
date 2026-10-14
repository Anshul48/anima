#!/usr/bin/env python3
"""Corrected rescore of a preserved pilot batch (no new episodes, $0).

Recomputes deterministic verdicts on preserved episode repos with the
calibrated checker (diff_only ignores pilot-generated cache artifacts).
Raw ledger outcomes are NEVER overwritten: this writes a separately
identified rescore artifact and reports raw-vs-corrected deltas.

Also validates confinement: on scratch copies, genuine unauthorized
changes must still fail diff_only.

Usage:
  STC_ROOT=/path/to/stc python3 rescore-pilot.py \
      --batch /tmp/live-pilot-kdfh9yx7 --out /tmp/rescore.json
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent


def load_script(name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, HERE / f"{name}.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def diff_only_ok(repo: Path, allowed: set[str], lp: Any) -> tuple[bool, set[str]]:
    out = subprocess.run(
        ["git", "status", "--porcelain"], cwd=repo, capture_output=True, text=True, check=True
    ).stdout
    changed = {
        n
        for n in out.split()
        if n not in ("M", "A", "??", "MM", "AM") and not lp.is_diff_only_ignored(n)
    }
    return changed == allowed, changed


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    batch = Path(args.batch)
    lp = load_script("live-pilot")
    pt = load_script("pilot-tasks")
    specs = {t["id"]: t for t in pt.dev_tasks("")}

    ledger_path = batch / "ledger.jsonl"
    ledger_sha = hashlib.sha256(ledger_path.read_bytes()).hexdigest()
    episodes = []
    for line in ledger_path.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        key = f"{row['policy']}-{row['task']}"
        repo = batch / key / "repo"
        spec = specs[row["task"]]
        corrected = lp.verdict(spec, repo)
        episodes.append(
            {
                "policy": row["policy"],
                "task": row["task"],
                "raw": row["verdict"],
                "corrected": corrected,
                "changed": corrected != row["verdict"],
            }
        )
        print(f"{key}: raw={row['verdict']} corrected={corrected}")

    # Confinement adversarial checks on a scratch copy (never the evidence).
    adv_src = batch / "b1-direct-bug-repair" / "repo"
    allowed = {"calc.py"}
    adv: dict[str, Any] = {}
    with tempfile.TemporaryDirectory(prefix="rescore-adv-") as td:
        repo = Path(td) / "repo"
        shutil.copytree(adv_src, repo, symlinks=True)
        ok, changed = diff_only_ok(repo, allowed, lp)
        adv["asis"] = {"ok": ok, "changed": sorted(changed)}
        (repo / "evil.py").write_text("print('unauthorized')\n", encoding="utf-8")
        ok, changed = diff_only_ok(repo, allowed, lp)
        adv["unauthorized_file_fails"] = {"ok": ok, "changed": sorted(changed)}
        (repo / "evil.py").unlink()
        cache = repo / "__pycache__" / "injected.pyc"
        cache.parent.mkdir(exist_ok=True)
        cache.write_bytes(b"\x00" * 16)
        ok, changed = diff_only_ok(repo, allowed, lp)
        adv["ignored_artifact_passes"] = {"ok": ok, "changed": sorted(changed)}

    rescore = {
        "artifact": "corrected-rescore-v1",
        "batch": str(batch),
        "ledger_sha256": ledger_sha,
        "checker": "live-pilot.verdict + DIFF_ONLY_IGNORE (cache artifacts only)",
        "episodes": episodes,
        "adversarial_confinement": adv,
        "notes": [
            "Raw ledger outcomes preserved; this artifact is separate.",
            "Per-task exclusions beyond cache artifacts are NOT adopted.",
            "n=3 preliminary scope unchanged; no policy superiority claim.",
        ],
    }
    Path(args.out).write_text(json.dumps(rescore, indent=1), encoding="utf-8")
    print(f"wrote {args.out}")

    ok_adv = (
        adv["unauthorized_file_fails"]["ok"] is False
        and adv["ignored_artifact_passes"]["ok"] is True
    )
    print("ADVERSARIAL:", "PASS" if ok_adv else "FAIL", json.dumps(adv))
    return 0 if ok_adv else 1


if __name__ == "__main__":
    sys.exit(main())
