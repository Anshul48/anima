#!/usr/bin/env python3
"""Product-journey qualification (coordinator-assisted, zero model calls).

Drives the REAL DSH runtime (sdk-minimal profile: real agent loop,
sessions, persistent bash) through the product acceptance journey with a
SCRIPTED provider (every model turn is a coordinator-authored decision):

  1. describe a feature -> 2. coordinator changes a repo -> 3. inspect a
  working preview + verified diff -> 4. request a refinement ->
  5. inspect the updated result.

Asserts on real session events (bash outputs), real disk state, and real
git diffs. Nothing here is a mock of the workspace: only the provider is
scripted, which is what makes the run quota-free AND deterministic.

Usage: STC_ROOT must point at the STC checkout (default: this repo).
  DSH_CHECKOUT (default /tmp/dsh-upstream) must be a built DSH checkout.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

STC_ROOT = Path(os.environ.get("STC_ROOT", Path(__file__).resolve().parents[2]))
DSH_CHECKOUT = Path(os.environ.get("DSH_CHECKOUT", "/tmp/dsh-upstream"))
VENV_BIN = STC_ROOT / ".venv" / "bin"
WRAPPER = STC_ROOT / "dsh-plugin-stc" / "scripts" / "dsh-bin.sh"
SCRIPTED = STC_ROOT / "dsh-plugin-scripted" / "src" / "index.ts"

sys.path.insert(0, str(DSH_CHECKOUT / "python" / "sdk" / "src"))

GREET_V1 = '''"""Tiny greeter CLI (product-journey fixture)."""

import argparse


def greet(name: str) -> str:
    return f"Hello, {name}!"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", default="world")
    args = parser.parse_args()
    print(greet(args.name))


if __name__ == "__main__":
    main()
'''

TEST_V1 = """from greet import greet


def test_greet() -> None:
    assert greet("ada") == "Hello, ada!"
"""

GREET_V2 = '''"""Tiny greeter CLI (product-journey fixture)."""

import argparse


def greet(name: str, shout: bool = False) -> str:
    text = f"Hello, {name}!"
    return text.upper() if shout else text


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", default="world")
    parser.add_argument("--shout", action="store_true")
    args = parser.parse_args()
    print(greet(args.name, args.shout))


if __name__ == "__main__":
    main()
'''

TEST_V2 = """from greet import greet


def test_greet() -> None:
    assert greet("ada") == "Hello, ada!"


def test_shout() -> None:
    assert greet("ada", shout=True) == "HELLO, ADA!"
"""

GREET_V3 = '''"""Tiny greeter CLI (product-journey fixture)."""

import argparse


def greet(name: str, shout: bool = False) -> str:
    if shout:
        return f"HELLO, {name.upper()}!!!"
    return f"Hello, {name}!"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", default="world")
    parser.add_argument("--shout", action="store_true")
    args = parser.parse_args()
    print(greet(args.name, args.shout))


if __name__ == "__main__":
    main()
'''

TEST_V3 = """from greet import greet


def test_greet() -> None:
    assert greet("ada") == "Hello, ada!"


def test_shout() -> None:
    assert greet("ada", shout=True) == "HELLO, ADA!!!"
"""


def write_file(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def git(repo: Path, *args: str) -> str:
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "journey",
        "GIT_AUTHOR_EMAIL": "journey@local",
        "GIT_COMMITTER_NAME": "journey",
        "GIT_COMMITTER_EMAIL": "journey@local",
    }
    return subprocess.run(
        ["git", *args], cwd=repo, env=env, capture_output=True, text=True, check=True
    ).stdout


def heredoc(path: str, content: str) -> str:
    return f"cat > {path} <<'JourneyEOF'\n{content}JourneyEOF"


def tool_turn(call_id: str, command: str) -> dict[str, Any]:
    call = {"toolCall": {"id": call_id, "name": "bash", "args": {"command": command}}}
    return {"blocks": [call], "finish": "tool-calls"}


def text_turn(text: str) -> dict[str, Any]:
    return {"blocks": [{"text": text}], "finish": "stop"}


def build_script(pytest: str, ruff: str, runner: str) -> list[dict[str, Any]]:
    return [
        # Turn 1: feature --shout.
        tool_turn("j1-inspect", "cat greet.py test_greet.py"),
        tool_turn("j1-edit-app", heredoc("greet.py", GREET_V2)),
        tool_turn("j1-edit-test", heredoc("test_greet.py", TEST_V2)),
        tool_turn("j1-gates", f"{pytest} -q && {ruff} check . && {ruff} format --check ."),
        tool_turn("j1-preview", f"{runner} greet.py --name ada --shout"),
        tool_turn("j1-diff", "git diff --stat && git status --porcelain"),
        text_turn("Feature done: --shout added, gates green, preview verified."),
        # Turn 2: refinement !!!.
        tool_turn("j2-edit-app", heredoc("greet.py", GREET_V3)),
        tool_turn("j2-edit-test", heredoc("test_greet.py", TEST_V3)),
        tool_turn("j2-gates", f"{pytest} -q && {ruff} check ."),
        tool_turn("j2-preview", f"{runner} greet.py --name ada --shout"),
        tool_turn("j2-diff", "git diff greet.py | head -40"),
        text_turn("Refinement done: shout now appends !!!, gates green."),
    ]


def event_texts(events: list[dict[str, Any]]) -> list[str]:
    """Extract tool/result text payloads in order."""
    out = []
    for e in events:
        if e.get("type") != "tool/result":
            continue
        msg = e.get("data", {}).get("message", {})
        chunks = []
        for b in msg.get("content", []) or []:
            if isinstance(b, dict) and b.get("type") == "text":
                chunks.append(b.get("text", ""))
        out.append("\n".join(chunks))
    return out


def check(name: str, cond: bool, detail: str = "") -> None:
    tag = "PASS" if cond else "FAIL"
    suffix = f" — {detail}" if detail and not cond else ""
    print(f"  [{tag}] {name}{suffix}")
    if not cond:
        raise AssertionError(f"journey check failed: {name} {detail}")


def main() -> int:
    from deepseek_harness import DeepSeekHarness  # type: ignore[import-not-found]

    assert WRAPPER.exists(), f"missing dsh wrapper: {WRAPPER}"
    assert SCRIPTED.exists(), f"missing scripted fixture: {SCRIPTED}"
    work = Path(tempfile.mkdtemp(prefix="product-journey-"))
    repo = work / "repo"
    repo.mkdir()
    write_file(repo / "greet.py", GREET_V1)
    write_file(repo / "test_greet.py", TEST_V1)
    git(repo, "init", "-q")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "init")
    print(f"repo: {repo}")

    pytest = f"{VENV_BIN}/python -m pytest"
    ruff = f"{VENV_BIN}/ruff"
    runner = f"{VENV_BIN}/python"
    script_path = work / "script.json"
    script_path.write_text(json.dumps(build_script(pytest, ruff, runner)), encoding="utf-8")
    patch_path = work / "scripted.patch.yml"
    patch_path.write_text(
        f"- insert:\n    - id: stc-scripted\n      name: '{SCRIPTED}'\n",
        encoding="utf-8",
    )
    home = work / "dsh-home"
    home.mkdir()

    with DeepSeekHarness(
        provider="scripted",
        model="scripted",
        cwd=str(repo),
        dsh_home=str(home),
        profile="sdk-minimal",
        patches=[str(patch_path)],
        dsh_bin=str(WRAPPER),
        env={"STC_SCRIPT_FILE": str(script_path)},
        request_timeout_seconds=300,
    ) as harness:
        session = harness.start_session("product-journey")
        print("turn 1: feature --shout")
        r1 = session.run("Add a --shout flag that uppercases the greeting.")
        print("turn 2: refinement !!!")
        r2 = session.run("Refinement: --shout should append !!! instead of !.")

    print("checks (turn 1):")
    t1 = event_texts(r1.events)
    check("6 bash results", len(t1) == 6, f"got {len(t1)}")
    check("inspect shows v1", 'return f"Hello, {name}!"' in t1[0])
    check("gates green", "2 passed" in t1[3] and "All checks passed" in t1[3], t1[3][:200])
    check("preview shouts", "HELLO, ADA!" in t1[4], t1[4][:200])
    check("diff touches both files", "greet.py" in t1[5] and "test_greet.py" in t1[5])
    check("finish completed", r1.finish_reason == "completed", str(r1.finish_reason))
    check("disk has v2", (repo / "greet.py").read_text().count("shout") >= 3)

    print("checks (turn 2):")
    t2 = event_texts(r2.events)
    check("5 bash results", len(t2) == 5, f"got {len(t2)}")
    check("gates green again", "2 passed" in t2[2], t2[2][:200])
    check("preview bangs", "HELLO, ADA!!!" in t2[3], t2[3][:200])
    check("diff shows refinement", "!!!" in t2[4])
    check("finish completed", r2.finish_reason == "completed", str(r2.finish_reason))
    check("disk has v3", "!!!" in (repo / "greet.py").read_text())
    print(f"JOURNEY-GREEN work={work} (kept for inspection)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
