#!/usr/bin/env python3
"""Generate pilot task sets: dev (6) + held-out twins (3) + manifest.

Each task: prompt + repo files + verdict spec (checker kinds implemented
by live-pilot.py). Twins are seeded content variants, disjoint by
construction (asserted: no shared identifiers with the dev twin).

Usage: python scripts/pilot-tasks.py <out-dir>
Writes <out-dir>/{dev,heldout}/<id>/task.json + <out-dir>/manifest.json.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

CALC_DEV = '''"""Calculator (pilot task fixture)."""


def total(values: list[int]) -> int:
    result = 0
    for v in values:
        result -= v
    return result
'''

CALC_TEST_DEV = """from calc import total


def test_total() -> None:
    assert total([2, 3]) == 5
"""

CALC_TWIN = '''"""Multiplier (pilot task fixture)."""


def product(values: list[int]) -> int:
    result = 1
    for v in values:
        result += v
    return result
'''

CALC_TEST_TWIN = """from mult import product


def test_product() -> None:
    assert product([2, 3]) == 6
"""

GREET_DEV = '''"""Greeter CLI (pilot task fixture)."""

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

GREET_TEST_DEV = """from greet import greet


def test_greet() -> None:
    assert greet("ada") == "Hello, ada!"
"""

BYE_TWIN = '''"""Farewell CLI (pilot task fixture)."""

import argparse


def farewell(name: str) -> str:
    return f"Goodbye, {name}."


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", default="world")
    args = parser.parse_args()
    print(farewell(args.name))


if __name__ == "__main__":
    main()
'''

BYE_TEST_TWIN = """from bye import farewell


def test_farewell() -> None:
    assert farewell("ada") == "Goodbye, ada."
"""

DOCS_INSERT_DEV = "Pilot provenance: this line was added by the evaluated agent.\n"
DOCS_FILE_DEV = "STC-PILOT-PROVENANCE.md"
DOCS_INSERT_TWIN = "Held-out provenance: this line was added by the evaluated agent.\n"
DOCS_FILE_TWIN = "STC-HELDOUT-PROVENANCE.md"

# Batch extension (dev-only; held-out twins sealed): cross-module plumbing,
# visible-UI DOM assertion, multi-file shared-helper extraction. The
# proposal's ambiguous-spec/ask-user task is NOT included: the single-shot
# session.run harness cannot do an interactive ask-user round.

TOOL_DEV = '''"""Tool layer (batch task fixture)."""


def tool_call(name: str, **kwargs: object) -> dict[str, object]:
    return {"name": name, "args": {}}
'''

RENDER_DEV = '''"""Render layer (batch task fixture)."""


def render(call: dict[str, object]) -> str:
    return f"call={call['name']}"
'''

TEST_CROSS_DEV = '''"""Cross-module plumbing test (batch task fixture)."""
from render import render
from tool import tool_call


def test_flag_plumbed() -> None:
    assert "FLAG" in render(tool_call("probe", flag=True))


def test_flag_absent_by_default() -> None:
    assert "FLAG" not in render(tool_call("probe"))
'''

APP_DEV = """<!doctype html>
<html>
  <body>
    <h1>Demo</h1>
  </body>
</html>
"""

TEST_UI_DEV = '''"""UI DOM assertion (batch task fixture)."""
from html.parser import HTMLParser
from pathlib import Path


class _ButtonFinder(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.found: list[dict[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "button":
            self.found.append({k: v or "" for k, v in attrs})


def test_submit_button_present() -> None:
    finder = _ButtonFinder()
    finder.feed(Path("app.html").read_text(encoding="utf-8"))
    assert any(b.get("id") == "submit-btn" for b in finder.found)


def test_submit_button_label() -> None:
    assert "Submit" in Path("app.html").read_text(encoding="utf-8")
'''

SCORE_A_DEV = '''"""Module A (batch task fixture)."""


def score_a(raw: int) -> int:
    if raw < 0:
        clamped = 0
    elif raw > 100:
        clamped = 100
    else:
        clamped = raw
    return clamped * 2
'''

SCORE_B_DEV = '''"""Module B (batch task fixture)."""


def score_b(raw: int) -> int:
    if raw < 0:
        clamped = 0
    elif raw > 100:
        clamped = 100
    else:
        clamped = raw
    return clamped + 1
'''

TEST_SHARED_DEV = '''"""Shared-helper behavior test (batch task fixture)."""
import ast
from pathlib import Path


def test_scores() -> None:
    from a import score_a
    from b import score_b

    assert (score_a(-5), score_a(50), score_a(150)) == (0, 100, 200)
    assert (score_b(-5), score_b(50), score_b(150)) == (1, 51, 101)


def test_shared_helper_exists() -> None:
    import util

    assert callable(util.clamp)
    assert (util.clamp(-5), util.clamp(50), util.clamp(150)) == (0, 50, 100)


def test_modules_use_shared_helper() -> None:
    for mod in ("a.py", "b.py"):
        tree = ast.parse(Path(mod).read_text(encoding="utf-8"))
        uses = False
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "util":
                uses = True
            elif isinstance(node, ast.Import):
                uses = uses or any(a.name.split(".")[0] == "util" for a in node.names)
        assert uses, mod
'''


def task(
    task_id: str,
    kind: str,
    prompt: str,
    files: dict[str, str],
    verdict: dict[str, Any],
) -> dict[str, Any]:
    return {"id": task_id, "kind": kind, "prompt": prompt, "files": files, "verdict": verdict}


def dev_tasks(docs_sample: str) -> list[dict[str, Any]]:
    return [
        task(
            "bug-repair",
            "bug-repair",
            "Fix the bug: `total([2, 3])` must equal 5. Keep the fix minimal; "
            "make the test suite pass.",
            {"calc.py": CALC_DEV, "test_calc.py": CALC_TEST_DEV},
            {
                "pytest": ["test_calc.py::test_total"],
                "gates": True,
                "diff_only": ["calc.py"],
            },
        ),
        task(
            "new-feature",
            "new-feature",
            "Add a --shout flag to greet.py that uppercases the greeting, "
            "with a test covering it. Keep the suite green.",
            {"greet.py": GREET_DEV, "test_greet.py": GREET_TEST_DEV},
            {
                "pytest": ["test_greet.py::test_greet"],
                "cli": {"argv": ["greet.py", "--name", "ada", "--shout"], "stdout": "HELLO, ADA!"},
                "gates": True,
                "diff_only": ["greet.py", "test_greet.py"],
            },
        ),
        task(
            "unfamiliar-docs",
            "unfamiliar-docs",
            f"Inside the docs copy, create {DOCS_FILE_DEV} containing exactly "
            "the provenance line below (and nothing else):\n"
            f"{DOCS_INSERT_DEV.strip()}\n"
            "Do not modify any other file.",
            {"docs/README.md": docs_sample, "docs/OTHER.md": "untouched\n"},
            {
                "file_equals": {f"docs/{DOCS_FILE_DEV}": DOCS_INSERT_DEV},
                "diff_only": [f"docs/{DOCS_FILE_DEV}"],
            },
        ),
        task(
            "cross-module",
            "cross-module",
            "Plumb a `flag` option from the tool call through to the rendered "
            "text: `render(tool_call('probe', flag=True))` must contain "
            "'FLAG', while `render(tool_call('probe'))` must not. Keep both "
            "modules' public shapes otherwise unchanged.",
            {"tool.py": TOOL_DEV, "render.py": RENDER_DEV, "test_cross.py": TEST_CROSS_DEV},
            {
                "pytest": ["test_cross.py"],
                "gates": True,
                "diff_only": ["tool.py", "render.py"],
            },
        ),
        task(
            "visible-ui",
            "visible-ui",
            'Add a submit button to app.html: a <button> with id="submit-btn" '
            'labeled "Submit". Keep the rest of the page unchanged.',
            {"app.html": APP_DEV, "test_ui.py": TEST_UI_DEV},
            {
                "pytest": ["test_ui.py"],
                "gates": True,
                "diff_only": ["app.html"],
            },
        ),
        task(
            "multi-file",
            "multi-file",
            "Extract the duplicated clamping logic from a.py and b.py into a "
            "shared util.clamp helper used by both modules. Behavior must be "
            "preserved exactly.",
            {
                "a.py": SCORE_A_DEV,
                "b.py": SCORE_B_DEV,
                "test_shared.py": TEST_SHARED_DEV,
            },
            {
                "pytest": ["test_shared.py"],
                "gates": True,
                "diff_only": ["a.py", "b.py", "util.py"],
            },
        ),
    ]


def twin_tasks(docs_sample: str) -> list[dict[str, Any]]:
    return [
        task(
            "bug-repair-twin",
            "bug-repair",
            "Fix the bug: `product([2, 3])` must equal 6. Keep the fix minimal; "
            "make the test suite pass.",
            {"mult.py": CALC_TWIN, "test_mult.py": CALC_TEST_TWIN},
            {
                "pytest": ["test_mult.py::test_product"],
                "gates": True,
                "diff_only": ["mult.py"],
            },
        ),
        task(
            "new-feature-twin",
            "new-feature",
            "Add a --loud flag to bye.py that uppercases the farewell, "
            "with a test covering it. Keep the suite green.",
            {"bye.py": BYE_TWIN, "test_bye.py": BYE_TEST_TWIN},
            {
                "pytest": ["test_bye.py::test_farewell"],
                "cli": {"argv": ["bye.py", "--name", "ada", "--loud"], "stdout": "GOODBYE, ADA."},
                "gates": True,
                "diff_only": ["bye.py", "test_bye.py"],
            },
        ),
        task(
            "unfamiliar-docs-twin",
            "unfamiliar-docs",
            f"Inside the docs copy, create {DOCS_FILE_TWIN} containing exactly "
            "the provenance line below (and nothing else):\n"
            f"{DOCS_INSERT_TWIN.strip()}\n"
            "Do not modify any other file.",
            {"docs/README.md": docs_sample, "docs/OTHER.md": "untouched\n"},
            {
                "file_equals": {f"docs/{DOCS_FILE_TWIN}": DOCS_INSERT_TWIN},
                "diff_only": [f"docs/{DOCS_FILE_TWIN}"],
            },
        ),
    ]


def main() -> int:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("pilot-tasks")
    stc_root = Path(__file__).resolve().parents[2]
    docs_sample = (stc_root / "docs" / "STC-DSH-RELEASE.md").read_text(encoding="utf-8")[:2000]
    dev = dev_tasks(docs_sample)
    twins = twin_tasks(docs_sample)
    # Disjointness: dev and twin task texts share no task-specific identifiers.
    dev_text = json.dumps(dev)
    for marker in ["product(", "mult.py", "bye.py", "--loud", "HELDOUT", "GOODBYE"]:
        assert marker not in dev_text, f"dev set leaks twin marker: {marker}"
    twin_text = json.dumps(twins)
    for marker in ["total([", "calc.py", "greet.py", "--shout", "PILOT-PROVENANCE", "HELLO, ADA"]:
        assert marker not in twin_text, f"twin set leaks dev marker: {marker}"
    manifest: dict[str, Any] = {"tasks": []}
    for lane, tasks in (("dev", dev), ("heldout", twins)):
        for t in tasks:
            d = out / lane / str(t["id"])
            d.mkdir(parents=True, exist_ok=True)
            blob = json.dumps(t, indent=2, sort_keys=True)
            (d / "task.json").write_text(blob, encoding="utf-8")
            digest = hashlib.sha256(blob.encode()).hexdigest()
            manifest["tasks"].append({"lane": lane, "id": t["id"], "sha256": digest})
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"wrote {len(dev)} dev + {len(twins)} held-out tasks to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
