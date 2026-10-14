#!/usr/bin/env python3
"""Map a pilot rescore + ledger to theoracle EpisodeResult JSONL.

Honest mapping (documented limits):
- completed: ledger outcome == "completed".
- evidenceComplete: true (ledger + preserved repos reproduce IDENTICAL).
- regressions: 0 when the CORRECTED verdict passes, else 1.
- faults: 0/0 (the pilot injects no faults).
- toolCalls: ledger event_types["tool/call"] (0 when absent).
- durationMs: -1 uniform placeholder (per-episode durations were not
  recorded; uniform value has no tiebreak effect).
- timedOut: false (no episode timed out).

Usage:
  python3 rescore-to-episodes.py --rescore rescore-v1.json \
      --ledger ledger.jsonl --out episodes.jsonl
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rescore", required=True)
    ap.add_argument("--ledger", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    rescore = json.loads(Path(args.rescore).read_text(encoding="utf-8"))
    ledger_rows = [
        json.loads(line) for line in Path(args.ledger).read_text(encoding="utf-8").splitlines()
    ]
    ledger = {(r["policy"], r["task"]): r for r in ledger_rows}
    episodes: list[dict[str, Any]] = []
    for ep in rescore["episodes"]:
        row = ledger[(ep["policy"], ep["task"])]
        episodes.append(
            {
                "policy": ep["policy"],
                "task": ep["task"],
                "completed": row.get("outcome") == "completed",
                "evidenceComplete": True,
                "regressions": 0 if ep["corrected"]["passed"] else 1,
                "faultsInjected": 0,
                "faultsRecovered": 0,
                "toolCalls": int(row.get("event_types", {}).get("tool/call", 0)),
                "durationMs": -1,
                "timedOut": False,
            }
        )
    Path(args.out).write_text(
        "\n".join(json.dumps(e, sort_keys=True) for e in episodes) + "\n", encoding="utf-8"
    )
    print(f"wrote {len(episodes)} episodes to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
