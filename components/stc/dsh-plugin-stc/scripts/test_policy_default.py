#!/usr/bin/env python3
"""Regression tests: selection-driven pilot policy default (T7 loop).

Covers resolve_policies() in live-pilot.py (explicit wins, recorded
selection narrows, corrupt/unknown fails closed to all POLICIES) and
the rescore→episodes mapping shape.

Quota-free: no model calls, no network, no live pilot run. Run with:
  python test_policy_default.py   # plain python, no deps
  python -m pytest test_policy_default.py -q
"""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
FAILS: list[str] = []


def load(name: str):  # type: ignore[no-untyped-def]
    spec = importlib.util.spec_from_file_location(name, HERE / f"{name}.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def check(name: str, cond: bool, detail: str = "") -> None:
    print(("pass " if cond else "FAIL ") + name + (f" :: {detail}" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def main() -> int:
    lp = load("live-pilot")
    real_path = lp.SELECTION_PATH
    with tempfile.TemporaryDirectory(prefix="seltest-") as td:
        tmp = Path(td)
        # 1. explicit wins
        policies, prov = lp.resolve_policies("b2-gated")
        check("explicit-wins", policies == ["b2-gated"] and "explicit" in prov, prov)
        # 2. explicit unknown refused
        try:
            lp.resolve_policies("nope")
            check("explicit-unknown-refused", False, "no ValueError")
        except ValueError:
            check("explicit-unknown-refused", True)
        # 3. missing file -> fallback all
        lp.SELECTION_PATH = tmp / "absent.json"
        policies, prov = lp.resolve_policies(None)
        check("missing-fallback", policies == lp.POLICIES and "fallback" in prov, prov)
        # 4. corrupt file -> fallback all
        bad = tmp / "bad.json"
        bad.write_text("{not json", encoding="utf-8")
        lp.SELECTION_PATH = bad
        policies, prov = lp.resolve_policies(None)
        check("corrupt-fallback", policies == lp.POLICIES and "fallback" in prov, prov)
        # 5. unknown id -> fallback all
        unk = tmp / "unk.json"
        unk.write_text(json.dumps({"selected_default": "zzz"}), encoding="utf-8")
        lp.SELECTION_PATH = unk
        policies, prov = lp.resolve_policies(None)
        check("unknown-id-fallback", policies == lp.POLICIES and "fallback" in prov, prov)
        # 6. valid selection narrows
        good = tmp / "good.json"
        good.write_text(json.dumps({"selected_default": "b1-direct"}), encoding="utf-8")
        lp.SELECTION_PATH = good
        policies, prov = lp.resolve_policies(None)
        check("valid-narrows", policies == ["b1-direct"] and "selection.json" in prov, prov)
        lp.SELECTION_PATH = real_path

    # 7. adapter mapping shape on synthetic input
    ad = load("rescore-to-episodes")
    assert hasattr(ad, "main")
    with tempfile.TemporaryDirectory(prefix="maptest-") as td:
        tmp = Path(td)
        rescore = {
            "episodes": [
                {
                    "policy": "b1-direct",
                    "task": "bug-repair",
                    "corrected": {"passed": True, "checks": {}},
                },
                {
                    "policy": "b2-gated",
                    "task": "new-feature",
                    "corrected": {"passed": False, "checks": {}},
                },
            ]
        }
        ledger = [
            {
                "policy": "b1-direct",
                "task": "bug-repair",
                "outcome": "completed",
                "event_types": {"tool/call": 5},
            },
            {
                "policy": "b2-gated",
                "task": "new-feature",
                "outcome": "completed",
                "event_types": {"tool/call": 9},
            },
        ]
        (tmp / "r.json").write_text(json.dumps(rescore), encoding="utf-8")
        (tmp / "l.jsonl").write_text(
            "\n".join(json.dumps(r) for r in ledger) + "\n", encoding="utf-8"
        )
        argv, sys.argv = (
            sys.argv,
            [
                "rescore-to-episodes.py",
                "--rescore",
                str(tmp / "r.json"),
                "--ledger",
                str(tmp / "l.jsonl"),
                "--out",
                str(tmp / "e.jsonl"),
            ],
        )
        try:
            check("adapter-rc", ad.main() == 0)
        finally:
            sys.argv = argv
        rows = [
            json.loads(line) for line in (tmp / "e.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        need = {
            "policy",
            "task",
            "completed",
            "evidenceComplete",
            "regressions",
            "faultsInjected",
            "faultsRecovered",
            "toolCalls",
            "durationMs",
            "timedOut",
        }
        check("adapter-keys", all(need <= set(r) for r in rows))
        by = {(r["policy"], r["task"]): r for r in rows}
        check(
            "adapter-pass-maps-clean",
            by[("b1-direct", "bug-repair")]["regressions"] == 0
            and by[("b1-direct", "bug-repair")]["toolCalls"] == 5,
        )
        check(
            "adapter-fail-maps-regression",
            by[("b2-gated", "new-feature")]["regressions"] == 1
            and by[("b2-gated", "new-feature")]["toolCalls"] == 9,
        )

    print("RESULT:", "FAIL " + str(FAILS) if FAILS else "PASS")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
