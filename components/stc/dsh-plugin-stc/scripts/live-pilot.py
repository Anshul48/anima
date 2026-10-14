#!/usr/bin/env python3
"""Live pilot runner: b1-direct vs b2-gated on real tasks (SDK-driven).

Each episode: fresh repo + fresh DSH home, real agent loop + bash tools,
policy injected as system prompt. Verdicts are deterministic checkers
(pytest nodes, CLI output, exact files, confined diffs, gates).

Spend safety (all enforced, all dry-validatable with --provider scripted):
- explicit --authorize-spend required for any non-scripted provider
- per-episode ceilings: --max-turns (watchdog), --max-tokens/call,
  --episode-timeout (request timeout)
- batch abort past 80% of --cap-usd; spend ledger per episode (JSONL)

Usage:
  live-pilot.py --tasks-dir <dir> --lane dev [--provider scripted]   # dry mechanics
  live-pilot.py --tasks-dir <dir> --lane dev --provider deepseek-official
      --model <sail-model-slug> --base-url $SAIL_BASE_URL --authorize-spend  # PAID

DeepSeek access is routed through Sail: the paid key is SAIL_API_KEY
(env first, then STC_ROOT/.env; DEEPSEEK_API_KEY accepted as fallback)
and the endpoint is --base-url (or SAIL_BASE_URL / DEEPSEEK_BASE_URL env).
The SDK forwards these as DEEPSEEK_API_KEY / DEEPSEEK_BASE_URL to the
runtime subprocess, which the llm-deepseek adapter honors (else official
https://api.deepseek.com). Key values never appear in the ledger.
"""

from __future__ import annotations

import argparse
import hashlib
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

POLICY_PROMPTS = {
    "b0-single-agent": (
        "You are a software engineer with full shell access. Solve the task "
        "however you see fit, using any tools available to you. Verify your "
        "solution by running the relevant checks. Finish with a short "
        "summary of what you did."
    ),
    "b1-direct": (
        "You are a software engineer. For the task: do the work directly "
        "with shell commands, then verify by re-running checks and "
        "inspecting outputs. Recover from a failure with at most one retry "
        "per step. Finish with a short summary."
    ),
    "b2-gated": (
        "You are a software engineer. For the task: FIRST inspect and state "
        "your plan (preview), then execute ONLY the planned steps, then "
        "verify by re-running checks and inspecting outputs. If a check "
        "fails, re-inspect before retrying (at most one retry per step). "
        "Finish with a short summary."
    ),
}

POLICIES = ["b0-single-agent", "b1-direct", "b2-gated"]

SELECTION_PATH = Path(__file__).resolve().parent.parent / "policy" / "selection.json"


def resolve_policies(explicit: str | None) -> tuple[list[str], str]:
    """Resolve which policies a batch runs. Returns (policies, provenance).

    Explicit --policies always wins. Else the recorded selection file
    narrows the default to the selected policy. Anything unreadable,
    malformed, or naming an unknown policy fails closed to all
    POLICIES with a `fallback:` provenance (caller prints it).
    """
    if explicit:
        wanted = [p.strip() for p in explicit.split(",") if p.strip()]
        unknown = [p for p in wanted if p not in POLICIES]
        if unknown:
            raise ValueError(f"unknown policy ids: {unknown} (known: {POLICIES})")
        return wanted, "explicit --policies"
    try:
        sel = json.loads(SELECTION_PATH.read_text(encoding="utf-8"))
        chosen = sel.get("selected_default")
        if chosen in POLICIES:
            return [chosen], f"selection.json ({SELECTION_PATH})"
    except (OSError, ValueError):
        pass
    return list(POLICIES), "fallback: all POLICIES (no valid selection.json)"


# Confined-diff (`diff_only`) ignore list: bytecode/cache artifacts the
# pilot run itself produces — the agent's own verification commands and
# this checker's pytest/ruff invocations — not agent misbehavior.
# Explicit and narrow on purpose: any real source-file addition or
# modification outside the task's declared set still fails the check.
DIFF_ONLY_IGNORE_DIR_NAMES = frozenset({"__pycache__", ".pytest_cache", ".ruff_cache"})
DIFF_ONLY_IGNORE_SUFFIXES = (".pyc", ".pyo")


def is_diff_only_ignored(path: str) -> bool:
    """True if a changed path is a known pilot-generated artifact."""
    stem = path.rstrip("/")
    if stem.endswith(DIFF_ONLY_IGNORE_SUFFIXES):
        return True
    return any(part in DIFF_ONLY_IGNORE_DIR_NAMES for part in Path(stem).parts)


def tool_turn(call_id: str, command: str) -> dict[str, Any]:
    call = {"toolCall": {"id": call_id, "name": "bash", "args": {"command": command}}}
    return {"blocks": [call], "finish": "tool-calls"}


def dry_script() -> list[dict[str, Any]]:
    """Mechanics probe (verdicts expected to FAIL; asserts pipeline only)."""
    return [
        tool_turn("d1", "pwd && ls"),
        tool_turn("d2", "echo probe-ok"),
        {"blocks": [{"text": "dry probe done."}], "finish": "stop"},
    ]


def run_cmd(repo: Path, argv: list[str], timeout: int = 120) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, cwd=repo, capture_output=True, text=True, timeout=timeout)


def git(repo: Path, *args: str) -> str:
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "pilot",
        "GIT_AUTHOR_EMAIL": "pilot@local",
        "GIT_COMMITTER_NAME": "pilot",
        "GIT_COMMITTER_EMAIL": "pilot@local",
    }
    return subprocess.run(
        ["git", *args], cwd=repo, env=env, capture_output=True, text=True, check=True
    ).stdout


def verdict(task: dict[str, Any], repo: Path) -> dict[str, Any]:
    """Apply deterministic checkers. Returns {passed, checks:{name: bool}}."""
    spec = task["verdict"]
    checks: dict[str, bool] = {}
    if "pytest" in spec:
        r = run_cmd(repo, [str(VENV_BIN / "python"), "-m", "pytest", "-q", *spec["pytest"]])
        checks["pytest"] = r.returncode == 0
    if "cli" in spec:
        cli = spec["cli"]
        r = run_cmd(repo, [str(VENV_BIN / "python"), *cli["argv"]])
        checks["cli"] = r.returncode == 0 and cli["stdout"] in r.stdout
    if "file_equals" in spec:
        ok = True
        for rel, expected in spec["file_equals"].items():
            p = repo / rel
            ok = ok and p.exists() and p.read_text(encoding="utf-8") == expected
        checks["file_equals"] = ok
    if "diff_only" in spec:
        names = git(repo, "status", "--porcelain").split()
        changed = {
            n
            for n in names
            if n not in ("M", "A", "??", "MM", "AM") and not is_diff_only_ignored(n)
        }
        allowed = set(spec["diff_only"])
        checks["diff_only"] = changed == allowed
    if spec.get("gates"):
        r1 = run_cmd(repo, [str(VENV_BIN / "ruff"), "check", "."])
        r2 = run_cmd(repo, [str(VENV_BIN / "python"), "-m", "pytest", "-q"])
        checks["gates"] = r1.returncode == 0 and r2.returncode == 0
    return {"passed": all(checks.values()), "checks": checks}


def usage_of(events: list[dict[str, Any]]) -> dict[str, int]:
    """Sum model usage across session events (tolerant of shape drift)."""
    tin = tout = 0
    for e in events:
        data = e.get("data", {}) if isinstance(e.get("data"), dict) else {}
        u = data.get("usage") or (data.get("message") or {}).get("usage") or {}
        if isinstance(u, dict):
            tin += int(u.get("inputTokens", 0) or 0)
            tout += int(u.get("outputTokens", 0) or 0)
    return {"input": tin, "output": tout}


def event_types(events: list[dict[str, Any]]) -> dict[str, int]:
    hist: dict[str, int] = {}
    for e in events:
        t = str(e.get("type", "?"))
        hist[t] = hist.get(t, 0) + 1
    return hist


def main() -> int:
    from deepseek_harness import DeepSeekHarness  # type: ignore[import-not-found]

    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks-dir", required=True)
    ap.add_argument("--lane", choices=["dev", "heldout"], default="dev")
    ap.add_argument("--confirm-heldout", action="store_true")
    ap.add_argument("--provider", default="scripted")
    ap.add_argument("--model", default="scripted")
    ap.add_argument(
        "--base-url",
        default=os.environ.get("SAIL_BASE_URL") or os.environ.get("DEEPSEEK_BASE_URL"),
        help="LLM endpoint (Sail when set); none = adapter default",
    )
    ap.add_argument("--authorize-spend", action="store_true")
    ap.add_argument("--cap-usd", type=float, default=5.0)
    ap.add_argument("--price-in", type=float, default=0.20, help="$/M input tokens")
    ap.add_argument("--price-out", type=float, default=0.80, help="$/M output tokens")
    ap.add_argument("--max-turns", type=int, default=30)
    ap.add_argument("--max-tokens", type=int, default=4000)
    ap.add_argument("--episode-timeout", type=int, default=900)
    ap.add_argument("--workdir")
    ap.add_argument(
        "--policies",
        default=None,
        help="comma-separated policy subset (default: recorded selection, else all)",
    )
    args = ap.parse_args()

    if args.lane == "heldout" and not args.confirm_heldout:
        print("REFUSED: held-out lane needs --confirm-heldout", file=sys.stderr)
        return 2
    paid = args.provider != "scripted"
    if paid and not args.authorize_spend:
        print("REFUSED: non-scripted provider needs --authorize-spend", file=sys.stderr)
        return 2
    api_key: str | None = None
    if paid:
        api_key = os.environ.get("SAIL_API_KEY", "") or os.environ.get("DEEPSEEK_API_KEY", "")
        if not api_key:
            dotenv = STC_ROOT / ".env"
            if dotenv.exists():
                for line in dotenv.read_text(encoding="utf-8").splitlines():
                    if line.startswith("SAIL_API_KEY=") or line.startswith("DEEPSEEK_API_KEY="):
                        api_key = line.partition("=")[2].strip().strip("'\"")
                        if api_key:
                            break
        if not api_key:
            print(
                "REFUSED: no SAIL_API_KEY (env or STC_ROOT/.env)",
                file=sys.stderr,
            )
            return 2

    tasks_dir = Path(args.tasks_dir)
    manifest = json.loads((tasks_dir / "manifest.json").read_text(encoding="utf-8"))
    task_ids = [t["id"] for t in manifest["tasks"] if t["lane"] == args.lane]
    work = Path(args.workdir or tempfile.mkdtemp(prefix="live-pilot-"))
    work.mkdir(parents=True, exist_ok=True)
    ledger_path = work / "ledger.jsonl"
    from urllib.parse import urlparse

    endpoint = urlparse(args.base_url).hostname if args.base_url else "official-default"
    print(
        f"work: {work} lane={args.lane} provider={args.provider} "
        f"model={args.model} endpoint={endpoint} cap=${args.cap_usd:.2f}"
    )

    try:
        policies, provenance = resolve_policies(args.policies)
    except ValueError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2
    print(f"policies: {','.join(policies)} ({provenance})")

    spend = 0.0
    results: list[dict[str, Any]] = []
    for policy in policies:
        for tid in task_ids:
            if spend >= 0.8 * args.cap_usd:
                print(f"ABORT: spend ${spend:.2f} past 80% of cap", file=sys.stderr)
                return 3
            task = json.loads(
                (tasks_dir / args.lane / tid / "task.json").read_text(encoding="utf-8")
            )
            ep = work / f"{policy}-{tid}"
            repo = ep / "repo"
            repo.mkdir(parents=True)
            for rel, content in task["files"].items():
                p = repo / rel
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(content, encoding="utf-8")
            git(repo, "init", "-q")
            git(repo, "add", "-A")
            git(repo, "commit", "-qm", "init")
            home = ep / "dsh-home"
            home.mkdir()
            env: dict[str, str] = {"DSH_SYSTEM_PROMPT": POLICY_PROMPTS[policy]}
            patches: list[str] = []
            if not paid:
                sp = ep / "script.json"
                sp.write_text(json.dumps(dry_script()), encoding="utf-8")
                env["STC_SCRIPT_FILE"] = str(sp)
                pp = ep / "scripted.patch.yml"
                pp.write_text(
                    f"- insert:\n    - id: stc-scripted\n      name: '{SCRIPTED}'\n",
                    encoding="utf-8",
                )
                patches.append(str(pp))
            else:
                # Paid runs route through Sail's strict OpenAI-compatible
                # gateway, which rejects the proprietary `dsh_session_log`
                # and `dsh_plugin_packages` request fields (400
                # INVALID_REQUEST). Both contributors are Cordis plugins
                # with a supported `enabled` toggle: disable them by
                # config override, no adapter fork needed.
                sp = ep / "sail.patch.yml"
                sp.write_text(
                    "- id: session-log-deepseek\n"
                    "  config:\n"
                    "    enabled: false\n"
                    "- id: plugin-package-inventory-deepseek\n"
                    "  config:\n"
                    "    enabled: false\n",
                    encoding="utf-8",
                )
                patches.append(str(sp))
            print(f"episode {policy}/{tid} ...", flush=True)
            events: list[dict[str, Any]] = []
            outcome = "completed"
            try:
                with DeepSeekHarness(
                    provider=args.provider,
                    model=args.model,
                    api_key=api_key,
                    base_url=args.base_url,
                    cwd=str(repo),
                    dsh_home=str(home),
                    profile="sdk-minimal",
                    patches=patches,
                    dsh_bin=str(WRAPPER),
                    env=env,
                    max_tokens=args.max_tokens,
                    request_timeout_seconds=args.episode_timeout,
                ) as harness:
                    session = harness.start_session(f"pilot-{policy}-{tid}")
                    res = session.run(task["prompt"])
                    events = [dict(e) for e in res.events]
            except Exception as exc:
                outcome = f"error: {type(exc).__name__}: {exc}"
            use = usage_of(events)
            cost = (use["input"] * args.price_in + use["output"] * args.price_out) / 1e6
            spend += cost
            try:
                v = verdict(task, repo)
            except Exception as exc:
                v = {"passed": False, "checks": {"verdict-error": str(exc)}}
            record = {
                "policy": policy,
                "task": tid,
                "outcome": outcome,
                "verdict": v,
                "usage": use,
                "usd_est": round(cost, 4),
                "spend_total": round(spend, 4),
                "event_types": event_types(events),
                "policy_prompt_sha256": hashlib.sha256(POLICY_PROMPTS[policy].encode()).hexdigest(),
            }
            results.append(record)
            with ledger_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(record) + "\n")
            print(f"  {outcome} passed={v['passed']} usd={cost:.4f} total=${spend:.2f}")

    passed = sum(1 for r in results if r["verdict"]["passed"])
    print(f"PILOT-DONE n={len(results)} passed={passed} spend=${spend:.2f}")
    print(f"ledger={ledger_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
