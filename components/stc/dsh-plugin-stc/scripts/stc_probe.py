"""stc_probe.py — quota-free backend quoting probe for the DSH STC bundle.

Runs under the STC venv python. Imports the backend builders (never the
scheduler/dispatcher) and prints exact argv/validation JSON to stdout.
Never spawns runs, never writes backend state.

Ops:
  outer   outer `stc run` argv via operator-console lab.build_backend_argv
  inner   inner harness argv via harnesses.preview_argv (worker/gateway)
  budget  validate a budget string via lab.parse_budget_via_backend

Exit 0 with {"ok": true, ...} or {"ok": false, "error": ...}.
Exit 2 on CLI misuse.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

CONSOLE = Path(__file__).resolve().parents[2] / "operator-console"
sys.path.insert(0, str(CONSOLE))


def op_outer(args: argparse.Namespace) -> dict[str, Any]:
    import lab  # type: ignore[import-not-found]

    argv = lab.build_backend_argv(
        Path(args.spec),
        args.mode,
        args.budget or "",
        args.choice or "",
        args.task_id or "",
        backend_root=Path(args.backend_root) if args.backend_root else None,
        exec_harness=args.exec_harness or "",
    )
    return {"argv": argv, "cwd": str(Path(args.backend_root or Path.cwd()))}


def op_inner(args: argparse.Namespace) -> dict[str, Any]:
    import harnesses  # type: ignore[import-not-found]

    quoted: dict[str, Any] = harnesses.preview_argv(
        args.harness,
        args.role,
        args.prompt or "preview",
        model=args.model,
        backend_root=Path(args.backend_root) if args.backend_root else None,
    )
    return quoted


def op_budget(args: argparse.Namespace) -> dict[str, Any]:
    import lab

    parsed = lab.parse_budget_via_backend(
        args.budget or "",
        backend_root=Path(args.backend_root) if args.backend_root else None,
    )
    return {"parsed": parsed}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="stc_probe")
    ap.add_argument("--op", required=True, choices=["outer", "inner", "budget"])
    ap.add_argument("--spec", default="")
    ap.add_argument("--mode", default="manual")
    ap.add_argument("--budget", default="")
    ap.add_argument("--choice", default="")
    ap.add_argument("--task-id", default="")
    ap.add_argument("--exec-harness", default="")
    ap.add_argument("--harness", default="mock")
    ap.add_argument("--role", default="worker")
    ap.add_argument("--prompt", default="preview")
    ap.add_argument("--model", default=None)
    ap.add_argument("--backend-root", default="")
    args = ap.parse_args(argv)
    try:
        if args.op == "outer":
            payload: dict[str, Any] = op_outer(args)
        elif args.op == "inner":
            payload = op_inner(args)
        else:
            payload = op_budget(args)
    except Exception as exc:  # probe must fail as JSON, never traceback-only
        print(json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"}))
        return 0
    print(json.dumps({"ok": True, **payload}, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
