"""FOLLOWUP live-exp: single parameterized probe through the REAL confined gateway.

One CLI call per invocation. Mirrors the P05-fix diag wiring exactly
(CLIModelGateway/codex backend, single `cli` TEST profile, shaped prompt,
confined argv, seeded scratch CODEX_HOME deleted afterwards) with ONE lever
varied per probe vs the recorded Gate-4 baseline (see readiness.md).

Env controls (all optional unless noted):
  LIVEXP_OUT        (required) probe evidence dir, under live-exp/attempt-1/
  LIVEXP_PROBE      probe id, e.g. P0-H0a (required; recorded + spend row)
  LIVEXP_SST_SRC    (required) file holding the SST prompt bytes for this leg
  LIVEXP_FRAME      baseline | h4a | h4b | h1a | h1b | h2a   (default baseline)
  LIVEXP_CONTEXT_FILE  file with the appended block body (h1a/h1b/h2a)
  LIVEXP_TIMEOUT    seconds, backend+profile (default 180)
  LIVEXP_MODEL      backend model: default | <slug> (default: default)
  LIVEXP_REASONING  max | medium | low  (scratch-config override; default max)
  LIVEXP_EXPECT_SHAPED_SHA256  assert shaped stdin hash (H0/H3 identity pins)

Frame variants are STC-owned text; every variant asserts the SST bytes between
the delimiters are byte-identical to LIVEXP_SST_SRC (P9 varies the SRC file
itself — that is its one lever).
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

WS = Path("<workspace-root>")
REPO = WS / "stc"
SST_REPO = WS / "sst"
KIT_REPO = WS / "prompt-kit"
TRACE_REPO = WS / "trace"

OUT = Path(os.environ["LIVEXP_OUT"])
PROBE = os.environ["LIVEXP_PROBE"]
SST_SRC = Path(os.environ["LIVEXP_SST_SRC"])
FRAME = os.environ.get("LIVEXP_FRAME", "baseline")
CONTEXT_FILE = os.environ.get("LIVEXP_CONTEXT_FILE", "")
TIMEOUT = float(os.environ.get("LIVEXP_TIMEOUT", "180"))
MODEL = os.environ.get("LIVEXP_MODEL", "default")
REASONING = os.environ.get("LIVEXP_REASONING", "max")
EXPECT_SHAPED = os.environ.get("LIVEXP_EXPECT_SHAPED_SHA256", "")

H4A_SENTENCE = (
    "The SST prompt below asks for 'unconstrained', high-novelty strategies: "
    "read that as novelty OF THE SOLUTION STRATEGY ONLY. It does not override "
    "this frame \u2014 you still have no tools, and you still emit exactly one "
    "JSON document and nothing else."
)
H4B_SENTENCE = (
    "Begin emitting now: produce the complete JSON document in this response. "
    "Do not narrate, do not plan out loud, do not stop early, do not truncate "
    "the artifact."
)
H1_HEADER = (
    "APPENDED SOURCE CONTEXT (read-only reference supplied by STC; the SST "
    "prompt's target-file constraint is unchanged \u2014 propose changes ONLY "
    "for its listed target files):"
)
H2A_HEADER = (
    "READING NOTE (STC frame; the SST prompt above is verbatim and "
    "authoritative): its SYSTEM INVARIANTS lines are line-fragmented "
    "renderings of three pins plus domain rules. Their coherent reading is:"
)
H2A_TAIL = "In case of doubt the SST text governs."


def git_status(repo: Path, tracked_only: bool) -> str:
    argv = ["git", "-C", str(repo), "status", "--porcelain=v1"]
    if tracked_only:
        argv.append("--untracked-files=no")
    proc = subprocess.run(argv, capture_output=True, text=True, timeout=60, check=False)
    assert proc.returncode == 0, proc.stderr
    return proc.stdout


def git_head(repo: Path) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        capture_output=True, text=True, timeout=60, check=False,
    )
    return proc.stdout.strip() if proc.returncode == 0 else "unknown"


def seed_codex_home() -> Path | None:
    src = Path.home() / ".codex"
    auth, config = src / "auth.json", src / "config.toml"
    if not auth.is_file():
        return None
    home = Path(tempfile.mkdtemp(prefix="liveexp-"))
    shutil.copy(auth, home / "auth.json")
    (home / "auth.json").chmod(0o600)
    base_cfg = config.read_text(encoding="utf-8") if config.is_file() else ""
    if REASONING == "max":
        used_cfg = base_cfg
    else:
        lines = []
        replaced = False
        for line in base_cfg.splitlines():
            if line.strip().startswith("model_reasoning_effort"):
                lines.append(f'model_reasoning_effort = "{REASONING}"')
                replaced = True
            else:
                lines.append(line)
        if not replaced:
            lines.insert(0, f'model_reasoning_effort = "{REASONING}"')
        used_cfg = "\n".join(lines) + ("\n" if lines else "")
    (home / "config.toml").write_text(used_cfg, encoding="utf-8")
    (OUT / "config-toml.txt").write_text(used_cfg, encoding="utf-8")
    (OUT / "config-reasoning.txt").write_text(REASONING + "\n", encoding="utf-8")
    return home


def apply_frame_variant(shaped: str, sst_text: str, begin: str, end: str) -> str:
    if FRAME == "baseline":
        return shaped
    if FRAME == "h4a":
        anchor = "no prose before or after it, no markdown fences, no commentary.\n"
        assert anchor in shaped, "h4a anchor missing"
        return shaped.replace(anchor, anchor + "\n" + H4A_SENTENCE + "\n", 1)
    if FRAME == "h4b":
        tail = "and nothing else."
        assert shaped.rstrip().endswith(tail), "h4b tail anchor missing"
        return shaped.rstrip() + "\n\n" + H4B_SENTENCE + "\n"
    if FRAME in ("h1a", "h1b", "h2a"):
        assert CONTEXT_FILE, f"{FRAME} needs LIVEXP_CONTEXT_FILE"
        body = Path(CONTEXT_FILE).read_text(encoding="utf-8")
        header = H1_HEADER if FRAME in ("h1a", "h1b") else H2A_HEADER
        block = header + "\n" + body.rstrip() + "\n"
        if FRAME == "h2a":
            block += H2A_TAIL + "\n"
        anchor = end + "\n"
        assert anchor in shaped, f"{FRAME} end-delimiter anchor missing"
        return shaped.replace(anchor, anchor + "\n" + block, 1)
    raise SystemExit(f"unknown LIVEXP_FRAME={FRAME!r}")


def main() -> int:
    from sst.gateway.contracts import (
        GatewayRequest,
        ModelCatalog,
        ProviderKind,
        ProviderProfile,
    )
    from sst.search.controller import SSTSearchController as _SST

    import stc.integration.cli_gateway as _gwmod
    from stc.integration.cli_gateway import (
        SST_PROMPT_BEGIN,
        SST_PROMPT_END,
        CLIGatewayBackend,
        CLIModelGateway,
        render_gateway_prompt,
        shape_gateway_prompt,
    )
    from stc.integration.harness_worker import SpendLedger, default_runner

    OUT.mkdir(parents=True, exist_ok=True)
    assert SST_SRC.is_file(), f"SST src missing: {SST_SRC}"
    sst_text = SST_SRC.read_text(encoding="utf-8")
    sst_sha = hashlib.sha256(sst_text.encode()).hexdigest()
    (OUT / "prompt-src-sha256.txt").write_text(f"{sst_sha}  {SST_SRC.name}\n")
    (OUT / "sst-source.txt").write_text(str(SST_SRC) + "\n")

    sst_before = git_status(SST_REPO, False)
    (OUT / "sst-before.txt").write_text(sst_before)
    if sst_before.strip():
        (OUT / "outcome.json").write_text(
            json.dumps({"probe": PROBE, "ok": False, "skipped": "sst dirty before leg"}, indent=2)
        )
        print("SKIP: sst dirty before leg (0 calls spent)", flush=True)
        return 3
    codex_home = seed_codex_home()
    if codex_home is None:
        (OUT / "outcome.json").write_text(
            json.dumps({"probe": PROBE, "ok": False, "skipped": "no codex login"}, indent=2)
        )
        print("SKIP: no operator codex login", flush=True)
        return 3

    # The live path renders messages ("user: " + bytes) BEFORE shaping
    # (CLIModelGateway.invoke -> backend.generate -> shape_gateway_prompt);
    # mirror it exactly so the pre-call hash pins the true stdin.
    rendered = render_gateway_prompt([{"role": "user", "content": sst_text}])
    shaped_base = shape_gateway_prompt(rendered)
    shaped = apply_frame_variant(shaped_base, sst_text, SST_PROMPT_BEGIN, SST_PROMPT_END)
    # SST-bytes-verbatim guard for every frame variant (P9 varies the SRC, not the frame).
    # Strip exactly the two join-separator newlines (content keeps its own trailing NL).
    seg = shaped.split(SST_PROMPT_BEGIN, 1)[1].split(SST_PROMPT_END, 1)[0]
    assert seg.startswith("\n") and seg.endswith("\n"), "delimiter framing broken"
    inner = seg[1:-1]
    assert inner == rendered, "SST bytes between delimiters differ from source"
    if FRAME in ("baseline",) or REASONING != "max" or MODEL != "default":
        pass
    if FRAME == "baseline":
        assert shaped == shaped_base, "baseline frame must equal shape_gateway_prompt"
    shaped_sha = hashlib.sha256(shaped.encode()).hexdigest()
    (OUT / "shaped-sha256.txt").write_text(shaped_sha + "  shaped-stdin\n")
    if EXPECT_SHAPED and EXPECT_SHAPED != shaped_sha:
        raise SystemExit(f"shaped hash {shaped_sha} != expected {EXPECT_SHAPED}")
    # Frame variants ride the REAL backend path by patching the STC-owned
    # shaping function in-process (argv/confinement/shaping-call-site all
    # unchanged; a winning variant becomes a real frame change). Baseline and
    # H3/model legs never patch: stdin must equal shape_gateway_prompt output.
    _orig_shape = _gwmod.shape_gateway_prompt
    if FRAME != "baseline":
        def _variant_shape(prompt_rendered: str, _o: Any = _orig_shape) -> str:
            return apply_frame_variant(
                _o(prompt_rendered), sst_text, SST_PROMPT_BEGIN, SST_PROMPT_END
            )
        _gwmod.shape_gateway_prompt = _variant_shape
        outcome_frame_patched = True
    else:
        outcome_frame_patched = False

    before_tracked = git_status(REPO, True)
    before_full = git_status(REPO, False)
    (OUT / "status-before-tracked.txt").write_text(before_tracked)
    (OUT / "status-before-full.txt").write_text(before_full)

    calls: list[dict[str, Any]] = []

    def recording_runner(
        argv: list[str],
        *,
        cwd: str,
        env: dict[str, str],
        timeout: float,
        stdin_text: str | None,
    ) -> subprocess.CompletedProcess[str]:
        try:
            proc = default_runner(argv, cwd=cwd, env=env, timeout=timeout, stdin_text=stdin_text)
        except subprocess.TimeoutExpired as exc:
            partial = exc.stdout if isinstance(exc.stdout, str) else ""
            calls.append(
                {"argv": argv, "cwd": cwd, "stdin_text": stdin_text,
                 "timeout": True, "partial_stdout": partial}
            )
            raise
        calls.append({"argv": argv, "cwd": cwd, "stdin_text": stdin_text, "proc": proc})
        return proc

    ledger = SpendLedger(OUT / "spend-ledger.jsonl")
    t0 = time.time()
    outcome: dict[str, Any] = {
        "probe": PROBE,
        "frame": FRAME,
        "frame_patched": outcome_frame_patched,
        "model": MODEL,
        "reasoning": REASONING,
        "timeout_s": TIMEOUT,
        "sst_bytes": len(sst_text.encode()),
        "sst_sha256": sst_sha,
        "shaped_bytes": len(shaped.encode()),
        "shaped_sha256": shaped_sha,
    }
    try:
        backend = CLIGatewayBackend(
            "codex",
            project_root=REPO,
            ledger=ledger,
            timeout=TIMEOUT,
            harness_env={"CODEX_HOME": str(codex_home)},
            runner=recording_runner,
        )
        # H3/model legs keep the prompt path identical; model routes via --model flag
        # through the profile's selected_model (gateway passes it to generate()).
        gateway = CLIModelGateway(backend)
        gateway.register_profile(
            ProviderProfile(
                name="cli",
                kind=ProviderKind.TEST,
                api_base="cli://local",
                selected_model=MODEL,
                timeout_seconds=int(TIMEOUT),
                catalog=ModelCatalog(),
            )
        )
        response = gateway.invoke(
            GatewayRequest(
                role="diverge",
                messages=[{"role": "user", "content": sst_text}],
                temperature=1.2,
                max_tokens=2048,
            )
        )
        wall = time.time() - t0
        content = response.content or ""
        outcome.update(
            {"ok": True, "wall_seconds": round(wall, 2),
             "content_chars": len(content), "content_head": content[:500],
             "resp_model": response.model, "resp_profile": response.profile}
        )
        parsed = _SST._parse_json_dict(content)
        branches = parsed.get("branches", []) if isinstance(parsed, dict) else []
        outcome["json_top_keys"] = sorted(parsed.keys()) if isinstance(parsed, dict) else []
        outcome["branch_count"] = len(branches) if isinstance(branches, list) else 0
        b0_valid, b0_code_chars = False, 0
        if isinstance(branches, list) and branches:
            b0 = branches[0] if isinstance(branches[0], dict) else {}
            code = _SST._clean_code(str(b0.get("proposed_changes", "")))
            b0_code_chars = len(code)
            b0_valid = bool(code)
            outcome["b0_has_title"] = bool(str(b0.get("strategy_title", "")).strip())
            outcome["b0_has_rationale"] = bool(str(b0.get("hypothesis_or_rationale", "")).strip())
            outcome["b0_code_chars"] = b0_code_chars
        outcome["s2_branches_valid"] = bool(b0_valid)
        outcome["s2_raw_fallback_nonempty"] = bool(_SST._clean_code(content))
        print(f"{PROBE} OK wall={wall:.1f}s chars={len(content)} "
              f"s2_valid={b0_valid} code_chars={b0_code_chars}", flush=True)
        rc = 0
    except Exception as exc:  # noqa: BLE001 - probe records, never raises
        wall = time.time() - t0
        outcome.update(
            {"ok": False, "wall_seconds": round(wall, 2),
             "error": f"{type(exc).__name__}: {exc}"}
        )
        err_l = str(exc).lower()
        outcome["looks_capacity"] = "at capacity" in err_l
        outcome["looks_timeout"] = "timed out" in err_l or "exit 124" in err_l
        print(f"{PROBE} FAILED wall={wall:.1f}s err={str(exc)[:220]}", flush=True)
        rc = 1
    finally:
        shutil.rmtree(codex_home, ignore_errors=True)
        outcome["codex_home_cleaned"] = not codex_home.exists()

    after_tracked = git_status(REPO, True)
    after_full = git_status(REPO, False)
    (OUT / "status-after-tracked.txt").write_text(after_tracked)
    (OUT / "status-after-full.txt").write_text(after_full)
    outcome["tracked_identical"] = after_tracked == before_tracked
    sst_after = git_status(SST_REPO, False)
    (OUT / "sst-after.txt").write_text(sst_after)
    outcome["sst_clean_after"] = not sst_after.strip()
    outcome["pins_after"] = {
        "sst": git_head(SST_REPO), "prompt_kit": git_head(KIT_REPO), "trace": git_head(TRACE_REPO),
    }

    if calls:
        call = calls[0]
        argv = [str(a) for a in call["argv"]]
        (OUT / "argv.txt").write_text(" ".join(argv) + "\n")
        (OUT / "cwd.txt").write_text(str(call["cwd"]) + "\n")
        (OUT / "prompt.txt").write_text(call["stdin_text"] or "")
        outcome["stdin_matches_precomputed"] = (call["stdin_text"] or "") == shaped
        if not outcome["stdin_matches_precomputed"]:
            outcome["VOID"] = "recorded stdin differs from precomputed shaped bytes"
        # Confinement assertions (recorded, fail-loud in outcome).
        checks = {
            "argv_codex_exec": "codex" in argv[0] and "exec" in argv,
            "argv_skip_git_check": "--skip-git-repo-check" in argv,
            "argv_readonly": "-s" in argv and "read-only" in argv,
            "argv_ephemeral": "--ephemeral" in argv,
            "argv_o_capture": "-o" in argv,
            "argv_stdin_dash": argv[-1] == "-",
            "argv_no_bypass": "--dangerously-bypass-approvals-and-sandbox" not in argv,
            "argv_model_flag_ok": (
                ("--model" not in argv) if MODEL == "default"
                else ("--model" in argv and MODEL in argv)
            ),
            "cwd_is_gateway_scratch": str(call["cwd"]).startswith("/tmp/stc-gateway-"),
        }
        outcome["confinement_checks"] = checks
        outcome["confined"] = all(checks.values())
        if call.get("timeout"):
            (OUT / "stdout.txt").write_text(call.get("partial_stdout") or "")
            (OUT / "stderr.txt").write_text(
                "TIMEOUT: harness stderr unrecoverable (process killed).\n")
            (OUT / "exit.txt").write_text("124\n")
            outcome["timeout_partial_bytes"] = len(
                (call.get("partial_stdout") or "").encode())
        else:
            proc = call["proc"]
            (OUT / "stdout.txt").write_text(proc.stdout or "")
            (OUT / "stderr.txt").write_text(proc.stderr or "")
            (OUT / "exit.txt").write_text(str(proc.returncode) + "\n")
            header_lines = [
                line for line in (proc.stderr or "").splitlines()
                if any(k in line.lower() for k in
                       ("codex", "model", "reasoning", "sandbox", "workdir", "version"))
            ][:20]
            (OUT / "header.txt").write_text("\n".join(header_lines) + "\n")
            outcome["header_reasoning_line"] = next(
                (l for l in header_lines if "reasoning" in l.lower()), "")
        stdin_b = len((call["stdin_text"] or "").encode())
        out_b = len((OUT / "stdout.txt").read_bytes())
        err_b = len((OUT / "stderr.txt").read_bytes())
        (OUT / "byte-counts.txt").write_text(
            f"stdin={stdin_b} stdout={out_b} stderr={err_b}\n")
    else:
        (OUT / "header.txt").write_text("NO-CALL\n")
        outcome["confined"] = False

    # F1 sidecar presence (full bytes live here on failure legs).
    sidecar = OUT / "spend-ledger.failures.jsonl"
    outcome["sidecar_present"] = sidecar.is_file()
    if sidecar.is_file():
        try:
            recs = [json.loads(l) for l in
                    sidecar.read_text(encoding="utf-8").splitlines() if l.strip()]
            outcome["sidecar_records"] = len(recs)
            if recs:
                outcome["sidecar_stderr_chars"] = len(recs[-1].get("stderr_full", ""))
                outcome["sidecar_stdout_chars"] = len(recs[-1].get("stdout_full", ""))
        except Exception as exc:  # noqa: BLE001 - record, never raise
            outcome["sidecar_read_error"] = str(exc)[:120]

    (OUT / "outcome.json").write_text(json.dumps(outcome, indent=2))
    # Cumulative spend row (one per probe = one CLI call, unless skipped).
    spend_path = REPO / "docs/builds/stc-integration/evidence/FOLLOWUP/live-exp/attempt-1/spend.jsonl"
    if "skipped" not in outcome:
        row = {"probe": PROBE, "frame": FRAME, "model": MODEL, "reasoning": REASONING,
               "ok": outcome.get("ok"), "wall_seconds": outcome.get("wall_seconds"),
               "out_bytes": len((OUT / "stdout.txt").read_bytes()) if (OUT / "stdout.txt").is_file() else 0,
               "exit": (OUT / "exit.txt").read_text().strip() if (OUT / "exit.txt").is_file() else "?"}
        with spend_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row) + "\n")
    print(json.dumps(outcome, indent=2), flush=True)
    return rc


if __name__ == "__main__":
    sys.exit(main())
