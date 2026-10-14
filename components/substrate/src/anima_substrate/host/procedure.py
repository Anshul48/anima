# Copyright 2026 Anshul48
# SPDX-License-Identifier: Apache-2.0
"""Successor-005 bounded procedure participant (S5 §1).

An ACCOUNTABLE EXECUTOR for caller-supplied procedures — not a sandbox.
A world advertises a creation-fixed procedure table (one
entry per bundled procedure: name + bundle sha256 pin + manifest
ref + step names); the `proc.exec@v1` service capability executes
table entries step by step inside the §1.4 invocation envelope
(argv-list exec, fresh per-step scratch cwd, allowlist env, captured
stdio with caps, timeout kill, interpreter pinning, bundle
re-verification, outside-scratch-write detection), recording
complete accountability data (ledger `proc_begin` + `invoke.proc`
+ `RESULT.json`, all cross-checkable).

Trust model (§8.1, carried verbatim in CONSUMER.md): callers supply
procedures AND bear their content risk. The host vouches ONLY that
(a) executed bytes equal advertised bytes (hash-pinned, re-verified
pre/post), (b) execution ran inside the §1.4 envelope (ENFORCED
items guaranteed, CONTRACTUAL items labeled — P11 network/
outside-state writes and P13 memory caps are NOT claimed), (c) the
recorded data is complete and recomputable, (d) interruption
landings are as specified (§1.7). `proc.exec` MUST be invoked only
via `run_procedure` (or adopt-path recovery): direct
`host.invoke("proc.exec")` without the `proc` block is denied by
the host.

Interruption (§1.7): re-run the interrupted step fresh in a new
scratch + adopt-if-complete via the parent-written DONE marker
(DONE present ⇒ parent reaped the child ⇒ child dead ⇒ scratch
stable). Recovery never spawns. Kill classes: process-crash only
(no fsync; power/media loss = disk-loss, LIMITS-2).

Stdlib-only. Every whole-file host write routes through
`atomic_write_text` / `atomic_write_bytes` (no open-"w",
no os.replace in this module — asserted by test_procedure.py).
"""

from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import signal
import subprocess
import time

from .minihost import (
    ContractViolation,
    MiniHost,
    atomic_write_bytes,
    atomic_write_text,
    maybe_crash_at,
)
from .resume import proc_begins, proc_prior_bundles, proc_succeeded

PROC_CAP = "proc.exec"
PROC_VER = "v1"

# §1.1/§1.4 pins.
TIMEOUT_CEILING_S = 600
STDOUT_CAP = 1024 * 1024
STDERR_CAP = 1024 * 1024
MANIFEST_NAME = "MANIFEST.json"
DONE_NAME = "DONE.json"
RESULT_NAME = "RESULT.json"
STDOUT_NAME = "stdout.log"
STDERR_NAME = "stderr.log"
HOST_STDIO_DIR = ".host-stdio"

# R-E: grant sizing adequate for minutes-long steps. A proc world
# holds 3600 s / 100 invokes; a proc-run root holds twice that so
# the §3 change leg (W2 beside W1) funds without operator input.
PROC_GRANT_LIMITS = {"max_cost_usd": 1.0, "max_time_s": 3600.0, "max_invocations": 100}
PROC_ROOT_HOLDINGS = {
    "max_cost_usd": 10.0,
    "max_time_s": 7200.0,
    "max_invocations": 1000,
}

# Pinned-child env vars a manifest `env_extra` may never override.
_PINNED_ENV = frozenset(
    {"PATH", "PYTHONDONTWRITEBYTECODE", "HOME", "TMPDIR", "PYTHONPATH"}
)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: str | os.PathLike) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def canonical_manifest_bytes(manifest: dict) -> bytes:
    return json.dumps(
        manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("ascii")


def utcnow() -> str:
    return datetime.now(UTC).isoformat()


def round_up_01(elapsed: float) -> float:
    """Grant/elapsed rounding: UP to 0.1 s (P14)."""
    return math.ceil(max(0.0, elapsed) * 10) / 10.0


# ------------------------------------------------- bundle validation
#
# Advertise-time checks (§1.1): manifest well-formed; every step has
# step/argv/declared_outputs/timeout_s; no absolute paths or `..` in
# bundle or declared outputs; timeout_s within the ceiling; argv list
# form (no shell exists in the executor); bundle hash recomputed
# over the staged bytes. Violation ⇒ ValueError naming the defect,
# zero ledger effect (all checks run before any append).


def _is_hex64(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(c in "0123456789abcdef" for c in value)
    )


def _is_safe_relpath(value: object) -> bool:
    if not isinstance(value, str) or not value or value.startswith("/"):
        return False
    if "\\" in value or value.startswith("~"):
        return False
    parts = value.split("/")
    if any(p in ("", ".", "..") for p in parts):
        return False
    return True


def _is_safe_segment(value: object) -> bool:
    return (
        isinstance(value, str)
        and bool(value)
        and "/" not in value
        and "\\" not in value
        and "\x00" not in value
        and value not in (".", "..")
    )


def validate_idem_key(key: object) -> str:
    if not _is_safe_segment(key):
        raise ValueError(
            f"idempotence key {key!r} must be a non-empty single path segment"
        )
    return key  # type: ignore[return-value]


def validate_procedure_name(name: object) -> str:
    if not isinstance(name, str) or not name:
        raise ValueError("procedure name must be a non-empty string")
    if any(
        c not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_.-"
        for c in name
    ):
        raise ValueError(
            f"procedure name {name!r} uses characters outside [A-Za-z0-9_.-]"
        )
    return name


def validate_manifest(manifest: object, what: str = "MANIFEST.json") -> dict:
    """Validate a parsed manifest; return it typed. Raises ValueError."""
    if not isinstance(manifest, dict):
        raise ValueError(f"{what}: manifest must be a JSON object")
    files = manifest.get("files")
    if not isinstance(files, dict):
        raise ValueError(f"{what}: 'files' must be a {{relpath: sha256}} object")
    for rel, digest in files.items():
        if not _is_safe_relpath(rel):
            raise ValueError(
                f"{what}: files key {rel!r} is not a "
                f"safe relpath (no absolute paths, no '..')"
            )
        if not _is_hex64(digest):
            raise ValueError(f"{what}: files[{rel!r}] is not a 64-hex sha256")
    steps = manifest.get("steps")
    if not isinstance(steps, list):
        raise ValueError(f"{what}: 'steps' must be a list")
    seen: set[str] = set()
    for i, step in enumerate(steps):
        tag = f"{what}: steps[{i}]"
        if not isinstance(step, dict):
            raise ValueError(f"{tag}: step must be an object")
        name = step.get("step")
        if not _is_safe_segment(name):
            raise ValueError(
                f"{tag}: 'step' must be a non-empty "
                f"single path segment (no '/', no '..')"
            )
        if name in seen:
            raise ValueError(f"{tag}: duplicate step name {name!r}")
        seen.add(name)
        argv = step.get("argv")
        if (
            not isinstance(argv, list)
            or not argv
            or not all(isinstance(a, str) for a in argv)
        ):
            raise ValueError(
                f"{tag}: 'argv' must be a non-empty "
                f"list of strings (list form only; no "
                f"shell exists in the executor)"
            )
        if any(not a for a in argv):
            raise ValueError(f"{tag}: 'argv' entries must be non-empty")
        outputs = step.get("declared_outputs")
        if not isinstance(outputs, list) or not all(
            isinstance(o, str) for o in outputs
        ):
            raise ValueError(f"{tag}: 'declared_outputs' must be a list of strings")
        for out in outputs:
            if not _is_safe_relpath(out):
                raise ValueError(
                    f"{tag}: declared output {out!r} is "
                    f"not a safe relpath (no absolute "
                    f"paths, no '..')"
                )
        timeout = step.get("timeout_s")
        if (
            isinstance(timeout, bool)
            or not isinstance(timeout, (int, float))
            or not (0 < timeout <= TIMEOUT_CEILING_S)
        ):
            raise ValueError(
                f"{tag}: 'timeout_s' must be a number in (0, {TIMEOUT_CEILING_S}]"
            )
        extra = step.get("env_extra", {})
        if not isinstance(extra, dict):
            raise ValueError(f"{tag}: 'env_extra' must be an object")
        for key, val in extra.items():
            if not isinstance(key, str) or not isinstance(val, str):
                raise ValueError(f"{tag}: 'env_extra' keys/values must be strings")
            if key in _PINNED_ENV or key.upper().endswith("_PROXY"):
                raise ValueError(
                    f"{tag}: 'env_extra' must not override pinned/proxy env {key!r}"
                )
    python_pin = manifest.get("python", "system")
    if python_pin != "system":
        raise ValueError(
            f"{what}: 'python' pin must be \"system\" (got {python_pin!r})"
        )
    if "inputs" in manifest and not isinstance(manifest["inputs"], list):
        raise ValueError(f"{what}: 'inputs' must be a list when present")
    return manifest


def verify_bundle(
    staged_dir: str | os.PathLike, expected_sha256: str | None = None
) -> dict:
    """Re-verify a staged bundle (P8): manifest hash + every file hash.

    Raises ValueError naming the first defect (missing MANIFEST,
    malformed manifest, manifest-hash mismatch vs `expected_sha256`,
    unpinned extra file, missing pinned file, file-hash mismatch,
    symlink). Returns the validated manifest on success.
    """
    staged = Path(staged_dir)
    manifest_path = staged / MANIFEST_NAME
    if not manifest_path.is_file() or manifest_path.is_symlink():
        raise ValueError(
            f"bundle {staged}: {MANIFEST_NAME} missing (or not a regular file)"
        )
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise ValueError(
            f"bundle {staged}: {MANIFEST_NAME} unparseable ({exc})"
        ) from exc
    validate_manifest(manifest, what=str(manifest_path))
    if expected_sha256 is not None:
        actual = sha256_bytes(canonical_manifest_bytes(manifest))
        if actual != expected_sha256:
            raise ValueError(
                f"bundle {staged}: manifest hash mismatch "
                f"(expected {expected_sha256[:16]}..., staged "
                f"{actual[:16]}...)"
            )
    pinned = dict(manifest["files"])
    seen: set[str] = set()
    for path in sorted(staged.rglob("*")):
        rel = path.relative_to(staged).as_posix()
        if path.is_symlink():
            raise ValueError(f"bundle {staged}: symlink {rel!r} refused")
        if path.is_dir():
            continue
        if rel == MANIFEST_NAME:
            continue
        seen.add(rel)
        if rel not in pinned:
            raise ValueError(
                f"bundle {staged}: unpinned extra file "
                f"{rel!r} (every staged byte must be pinned)"
            )
        if sha256_file(path) != pinned[rel]:
            raise ValueError(
                f"bundle {staged}: file {rel!r} hash "
                f"mismatch (staged bytes differ from pin)"
            )
    missing = sorted(set(pinned) - seen)
    if missing:
        raise ValueError(
            f"bundle {staged}: pinned file(s) missing from stage: {missing}"
        )
    return manifest


def stage_bundle(
    bundle_dir: str | os.PathLike, dest_dir: str | os.PathLike
) -> tuple[dict, str]:
    """Validate the source bundle, stage a host-owned copy, re-verify it.

    Returns (manifest, bundle_sha256). Raises ValueError naming the
    defect (source validation, symlink, copy failure, staged
    re-verification). A failed stage removes its partial dest dir.
    """
    src = Path(bundle_dir)
    if not src.is_dir():
        raise ValueError(f"bundle {src}: not a directory")
    manifest_path = src / MANIFEST_NAME
    if not manifest_path.is_file() or manifest_path.is_symlink():
        raise ValueError(
            f"bundle {src}: {MANIFEST_NAME} missing (or not a regular file)"
        )
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise ValueError(f"bundle {src}: {MANIFEST_NAME} unparseable ({exc})") from exc
    validate_manifest(manifest, what=str(manifest_path))
    dest = Path(dest_dir)
    if dest.exists():
        raise ValueError(f"bundle stage {dest}: dest already exists")
    try:
        for path in sorted(src.rglob("*")):
            rel = path.relative_to(src)
            if path.is_symlink():
                raise ValueError(f"bundle {src}: symlink {rel.as_posix()!r} refused")
            if path.is_dir():
                (dest / rel).mkdir(parents=True, exist_ok=True)
                continue
            if not _is_safe_relpath(rel.as_posix()):
                raise ValueError(f"bundle {src}: unsafe relpath {rel.as_posix()!r}")
            atomic_write_bytes(dest / rel, path.read_bytes())
        staged = verify_bundle(dest)
    except Exception:
        shutil.rmtree(dest, ignore_errors=True)
        raise
    bundle_sha = sha256_bytes(canonical_manifest_bytes(staged))
    return staged, bundle_sha


# ------------------------------------------------- envelope (P1–P7)
#
# P1 argv-list exec (shell=False always; no string-command path exists
# in this module) / P2 fresh per-step scratch cwd / P3
# allowlist-built env / P4 stdin devnull / P5 capture + 1 MiB caps /
# P6 timeout kill (POSIX group kill; Windows best-effort) / P7
# interpreter pinning (recorded; PROC_PY override must match).


def build_env(scratch: str | os.PathLike, env_extra: dict) -> tuple[dict, list[str]]:
    """P3: allowlist-built child env. Returns (env, sorted env_keys)."""
    box = str(scratch)
    env = {
        "PATH": os.environ.get("PATH", ""),
        "PYTHONDONTWRITEBYTECODE": "1",
        "HOME": box,
        "TMPDIR": box,
    }
    for key, val in env_extra.items():
        env[key] = val
    return env, sorted(env)


def resolve_interpreter(argv0: str, env: dict) -> str:
    """Resolve argv[0] to the binary Popen will exec (P7).

    No-slash names resolve via the CHILD's PATH (the same lookup
    Popen performs); slash paths are used as-is. Raises
    ContractViolation (refuse before spawn) when unresolvable, when
    the target is missing/not-a-file, or when an explicit PROC_PY
    override is set and differs from the resolution.
    """
    if "/" in argv0 or (os.sep == "\\" and "\\" in argv0):
        resolved = argv0
    else:
        resolved = shutil.which(argv0, path=env.get("PATH", "")) or ""
        if not resolved:
            raise ContractViolation(
                f"interpreter pin: {argv0!r} resolves to nothing on "
                f"the child PATH; refusing, not guessing"
            )
    if not Path(resolved).is_file():
        raise ContractViolation(
            f"interpreter pin: resolved {resolved!r} is not a file; "
            f"refusing, not guessing"
        )
    pinned = os.environ.get("PROC_PY", "").strip()
    if pinned:
        try:
            same = os.path.realpath(resolved) == os.path.realpath(pinned)
        except OSError:
            same = False
        if not same or not Path(pinned).is_file():
            raise ContractViolation(
                f"interpreter pin mismatch: resolved {resolved!r} "
                f"!= PROC_PY {pinned!r}; refusing, not guessing"
            )
    return resolved


def probe_version(interpreter: str) -> str:
    """Best-effort `sys.version` probe (host plumbing, no ledger entry).

    Returns "" for non-Python interpreters (documented: the version
    field records the Python version when the interpreter is Python).
    """
    try:
        proc = subprocess.Popen(
            [interpreter, "-c", "import sys; print(sys.version)"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            shell=False,
            env={"PATH": os.environ.get("PATH", ""), "PYTHONDONTWRITEBYTECODE": "1"},
        )
        try:
            out, _ = proc.communicate(timeout=30)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate()
            return ""
        if proc.returncode != 0:
            return ""
        return out.decode("utf-8", "replace").strip()
    except OSError:
        return ""


def _kill_group(proc: subprocess.Popen) -> None:
    """P6 kill: POSIX process-group SIGKILL; Windows best-effort."""
    if os.name == "posix":
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except (OSError, ProcessLookupError):
            pass
    try:
        proc.kill()
    except OSError:
        pass


# ------------------------------------------------- P9 state snapshot
#
# ENFORCED-detect: pre/post content-hash snapshots of the run root
# OUTSIDE the step scratch; any new/modified/removed file or dir ⇒
# the step FAILS (error-invoke names the files). Content-compare
# (sha256; mtimes recorded for forensics only); symlinks recorded by
# target, never followed. The compare runs post-wait + post-DONE,
# pre-result_ref (R-E); the parent writes NOTHING outside the step
# scratch between the snapshots, so the exemption set is empty by
# construction (collection + RESULT land after the compare).


def snapshot_state(root: str | os.PathLike, exclude: str | os.PathLike) -> dict:
    """Snapshot {files: {rel: [sha256, size]}, links: {rel: target},
    dirs: [rel...]} under root, excluding the `exclude` subtree."""
    base = Path(root)
    excl = str(Path(exclude))
    files: dict[str, list] = {}
    links: dict[str, str] = {}
    dirs: set[str] = set()
    for path in sorted(base.rglob("*")):
        spath = str(path)
        if spath == excl or spath.startswith(excl + os.sep):
            continue
        rel = path.relative_to(base).as_posix()
        if path.is_symlink():
            links[rel] = os.readlink(path)
        elif path.is_dir():
            dirs.add(rel)
        elif path.is_file():
            files[rel] = [
                sha256_file(path),
                path.stat().st_size,
                path.stat().st_mtime_ns,
            ]
    return {"files": files, "links": links, "dirs": sorted(dirs)}


def compare_snapshots(before: dict, after: dict) -> list[str]:
    """Content diffs outside the scratch: new/modified/removed/type
    changes, sorted. Empty ⇒ the child wrote nothing observable."""
    diffs: list[str] = []
    kinds = {rel: "file" for rel in before["files"]}
    kinds.update({rel: "link" for rel in before["links"]})
    kinds.update({rel: "dir" for rel in before["dirs"]})
    kinds_after = {rel: "file" for rel in after["files"]}
    kinds_after.update({rel: "link" for rel in after["links"]})
    kinds_after.update({rel: "dir" for rel in after["dirs"]})
    for rel in sorted(set(kinds) | set(kinds_after)):
        was, now = kinds.get(rel), kinds_after.get(rel)
        if was != now:
            diffs.append(f"{rel}: {was or 'absent'} -> {now or 'absent'}")
        elif was == "file" and before["files"][rel][0] != after["files"][rel][0]:
            diffs.append(f"{rel}: content changed")
        elif was == "link" and before["links"][rel] != after["links"][rel]:
            diffs.append(f"{rel}: link retargeted")
    return diffs


def scratch_inventory(scratch: str | os.PathLike) -> tuple[list, list]:
    """(files, links) under scratch, lstat-based, never following links.

    Returns ([(rel, size)], [(rel, target)]), sorted. The host stdio
    dir is parent-owned and excluded from the undeclared scan.
    """
    box = Path(scratch)
    files: list[tuple[str, int]] = []
    links: list[tuple[str, str]] = []
    if not box.is_dir():
        return files, links
    for path in sorted(box.rglob("*")):
        rel = path.relative_to(box).as_posix()
        if rel == HOST_STDIO_DIR or rel.startswith(HOST_STDIO_DIR + "/"):
            continue
        if path.is_symlink():
            links.append((rel, os.readlink(path)))
        elif path.is_file():
            files.append((rel, path.stat().st_size))
    return files, links


# ------------------------------------------------- gates + execution
#
# Invoke-time gates (all before any spawn; table-miss/collision/
# interpreter/lifecycle/capability/authority refuse with a recorded
# `deny` and zero child execution): (1) callee active, (2) cap
# advertised, (3) authority held, (4) (procedure, bundle) in the
# creation-fixed table, (5) no idempotence-key collision across
# bundles, (6) interpreter resolvable + pin-matching. Bundle
# pre-verification failure records an error-invoke (not a deny):
# the step was attempted and refused on its bytes.


def table_entry(world, procedure: str):
    for entry in world.procedures or []:
        if entry.get("name") == procedure:
            return entry
    return None


def _deny(host: MiniHost, caller: str, reason: str, detail: dict | None = None) -> None:
    host.deny(caller, "invoke", reason, detail)


def pre_gates(
    host: MiniHost, world_id: str, procedure: str, bundle_sha256: str, idem_key: str
) -> dict:
    """Run gates (1)–(5). Returns the table entry. Raises on refusal."""
    world = host.worlds.get(world_id)
    if world is None:
        _deny(host, world_id, f"unknown callee {world_id!r}")
        raise ContractViolation(f"unknown callee {world_id!r}")
    if world.lifecycle != "active":
        reason = f"callee {world_id!r} not active (state={world.lifecycle})"
        _deny(host, world_id, reason)
        raise ContractViolation(reason)
    cap = next(
        (c for c in world.capabilities if c.name == PROC_CAP and c.version == PROC_VER),
        None,
    )
    if cap is None:
        reason = f"{world_id!r} does not advertise {PROC_CAP}@{PROC_VER}"
        _deny(host, world_id, reason)
        raise ContractViolation(reason)
    if cap.required_authority and cap.required_authority not in world.authorities:
        reason = f"{world_id!r} lacks {cap.required_authority} for {PROC_CAP}"
        _deny(host, world_id, reason)
        raise ContractViolation(reason)
    entry = table_entry(world, procedure)
    if entry is None or entry.get("bundle_sha256") != bundle_sha256:
        reason = (
            f"{world_id!r} procedure table has no "
            f"({procedure!r}, bundle {bundle_sha256[:16]}...) "
            f"(fixed at creation; new content needs a new world)"
        )
        _deny(
            host,
            world_id,
            reason,
            {"procedure": procedure, "bundle_sha256": bundle_sha256},
        )
        raise ContractViolation(reason)
    priors = proc_prior_bundles(host, idem_key)
    if priors and bundle_sha256 not in priors:
        reason = (
            f"idempotence key collision across content: key "
            f"{idem_key!r} already recorded bundle(s) "
            f"{sorted(p[:16] for p in priors)}; refusing "
            f"{bundle_sha256[:16]}..."
        )
        _deny(
            host,
            world_id,
            reason,
            {"idem_key": idem_key, "bundle_sha256": bundle_sha256},
        )
        raise ValueError(reason)
    return entry


def _cap_stream(data: bytes, cap: int) -> tuple[bytes, bool]:
    if len(data) > cap:
        return data[:cap], True
    return data, False


def _artifact_record(rel: str, data: bytes) -> dict:
    return {"relpath": rel, "sha256": sha256_bytes(data), "bytes": len(data)}


def stage_inputs(scratch: str | os.PathLike, inputs: dict | None) -> dict[str, str]:
    """Stage caller inputs under <scratch>/inputs/; return {name: sha256}.

    Values may be bytes (staged directly) or str/Path (file read,
    staged by copy). Names must be safe relpaths; symlinks refused.
    """
    hashes: dict[str, str] = {}
    if not inputs:
        return hashes
    dest = Path(scratch) / "inputs"
    for name, value in inputs.items():
        if not _is_safe_relpath(name):
            raise ValueError(f"input {name!r} is not a safe relpath")
        if isinstance(value, (bytes, bytearray)):
            data = bytes(value)
        elif isinstance(value, (str, os.PathLike)):
            src = Path(value)
            if src.is_symlink() or not src.is_file():
                raise ValueError(
                    f"input {name!r}: {src} is not a regular file (symlinks refused)"
                )
            data = src.read_bytes()
        else:
            raise ValueError(
                f"input {name!r}: expected bytes or a "
                f"file path, got {type(value).__name__}"
            )
        atomic_write_bytes(dest / name, data)
        hashes[name] = sha256_bytes(data)
    return hashes


def _collect_declared(
    scratch: Path, declared: list[str], dest_dir: Path
) -> tuple[list[dict], list[dict]]:
    """Collect declared outputs scratch→dest (copies). Returns
    (artifacts, undeclared_present). Raises ValueError naming a
    missing/non-file/symlink declared output (child broke its
    contract — loud, no silent gaps)."""
    artifacts: list[dict] = []
    for rel in declared:
        src = scratch / rel
        if src.is_symlink() or not src.is_file():
            raise ValueError(
                f"declared output {rel!r} missing (or not a regular "
                f"file — symlinks refused); the child broke its "
                f"output contract"
            )
        data = src.read_bytes()
        atomic_write_bytes(dest_dir / rel, data)
        artifacts.append(_artifact_record(rel, data))
    declared_set = set(declared)
    undeclared: list[dict] = []
    files, links = scratch_inventory(scratch)
    for rel, size in files:
        if rel == DONE_NAME or rel.startswith("inputs/") or rel in declared_set:
            continue
        undeclared.append({"relpath": rel, "bytes": size})
    for rel, _ in links:
        if rel not in declared_set:
            # Symlink: lstat size (the target is never followed).
            size = (scratch / rel).lstat().st_size
            undeclared.append({"relpath": rel, "bytes": size})
    undeclared.sort(key=lambda d: d["relpath"])
    return artifacts, undeclared


def _proc_block_base(
    procedure: str, bundle_sha256: str, idem_key: str, step: str, attempt: int
) -> dict:
    return {
        "procedure": procedure,
        "bundle_sha256": bundle_sha256,
        "idem_key": idem_key,
        "step": step,
        "attempt": attempt,
        "exit_code": None,
        "stdout_sha256": sha256_bytes(b""),
        "stdout_bytes": 0,
        "stderr_sha256": sha256_bytes(b""),
        "stderr_bytes": 0,
        "truncated_stdout": False,
        "truncated_stderr": False,
        "artifacts": [],
        "undeclared_present": [],
        "outside_writes": [],
        "elapsed_s": 0.0,
        "timed_out": False,
        "recovered": False,
    }


def _args_ref_for(
    host: MiniHost,
    world_id: str,
    procedure: str,
    bundle_sha256: str,
    idem_key: str,
    step: str,
    input_hashes: dict,
) -> str:
    # New documented step shape (§1.5): task_id scopes the key so the
    # sched (capability, task_id, step) matcher never collides across
    # proc runs; C2/C3 shapes do NOT apply to procedure steps.
    return host.store_args(
        world_id,
        f"proc-{idem_key}-{step}",
        {
            "task_id": f"{procedure}:{idem_key}",
            "step": step,
            "procedure": procedure,
            "bundle_sha256": bundle_sha256,
            "idem_key": idem_key,
            "input_refs": sorted(input_hashes),
        },
    )


def run_step(
    host: MiniHost,
    root: str | os.PathLike,
    world_id: str,
    procedure: str,
    bundle_sha256: str,
    step: str,
    idem_key: str,
    inputs: dict | None = None,
) -> dict:
    """Execute ONE step as a fresh attempt. Returns the success entry.

    Refusals (gates) record a `deny` and raise with zero spawn;
    failures record an error-invoke and raise (TimeoutError on
    timeout, RuntimeError on nonzero exit, ValueError on
    bytes/contract defects). A step already succeeded under the key
    is refused (skip-match applies — use run_procedure).
    """
    validate_idem_key(idem_key)
    entry = pre_gates(host, world_id, procedure, bundle_sha256, idem_key)
    if (bundle_sha256, idem_key, step) in proc_succeeded(host):
        raise RuntimeError(
            f"step {step!r} already succeeded under key "
            f"{idem_key!r}; skip-match applies (no re-execution)"
        )
    base = Path(root)
    world = host.worlds[world_id]
    staged = Path(world.instance_state_dir) / "procedures" / procedure
    attempt = len(proc_begins(host, idem_key, step)) + 1
    args_ref = _args_ref_for(
        host, world_id, procedure, bundle_sha256, idem_key, step, {}
    )
    # Bundle pre-verification (P8): failure ⇒ error-invoke, no spawn.
    try:
        manifest = verify_bundle(staged, bundle_sha256)
    except ValueError as exc:
        proc = _proc_block_base(procedure, bundle_sha256, idem_key, step, attempt)
        # Eager: the except-as target is deleted at block end.
        refuse_text = f"bundle pre-verify refused: {exc}"

        def _refuse() -> str:
            raise ValueError(refuse_text)

        host.invoke(
            world_id,
            world_id,
            PROC_CAP,
            PROC_VER,
            args_ref,
            _refuse,
            cost_usd=0.0,
            time_s=0.0,
            extra={"proc": proc},
        )
        raise
    step_def = next((s for s in manifest["steps"] if s.get("step") == step), None)
    if step_def is None:  # table/manifest skew: fail closed
        proc = _proc_block_base(procedure, bundle_sha256, idem_key, step, attempt)

        def _skew() -> str:
            raise ValueError(
                f"table/manifest skew: step {step!r} not in the verified manifest"
            )

        host.invoke(
            world_id,
            world_id,
            PROC_CAP,
            PROC_VER,
            args_ref,
            _skew,
            cost_usd=0.0,
            time_s=0.0,
            extra={"proc": proc},
        )
        raise ValueError(f"table/manifest skew for step {step!r}")
    if step not in entry.get("steps", []):  # same class, other side
        proc = _proc_block_base(procedure, bundle_sha256, idem_key, step, attempt)

        def _skew2() -> str:
            raise ValueError(
                f"table/manifest skew: step {step!r} not in the advertised table"
            )

        host.invoke(
            world_id,
            world_id,
            PROC_CAP,
            PROC_VER,
            args_ref,
            _skew2,
            cost_usd=0.0,
            time_s=0.0,
            extra={"proc": proc},
        )
        raise ValueError(f"table/manifest skew for step {step!r}")
    argv = list(step_def["argv"])
    declared = list(step_def["declared_outputs"])
    timeout = float(step_def["timeout_s"])
    env_extra = dict(step_def.get("env_extra", {}))
    # Scratch BEFORE proc_begin: input staging may fail with zero
    # ledger effect (partial stage removed); a kill here leaves a
    # benign pre-begin orphan (never read — L1 "no trace").
    scratch = base / "state" / "proc-scratch" / idem_key / f"{step}-attempt{attempt}"
    if scratch.exists():
        raise ValueError(
            f"scratch {scratch} already exists (fail-closed: refusing to reuse)"
        )
    scratch.mkdir(parents=True)
    try:
        input_hashes = stage_inputs(scratch, inputs)
    except Exception:
        shutil.rmtree(scratch, ignore_errors=True)
        raise
    args_ref = _args_ref_for(
        host, world_id, procedure, bundle_sha256, idem_key, step, input_hashes
    )
    env, env_keys = build_env(scratch, env_extra)
    try:
        interpreter = resolve_interpreter(argv[0], env)
    except ContractViolation as exc:
        _deny(host, world_id, str(exc), {"procedure": procedure, "step": step})
        raise
    version = probe_version(interpreter)
    invoke_id = f"proc-{idem_key}-{step}-a{attempt}"
    host.append(
        "proc_begin",
        {
            "invoke_id": invoke_id,
            "idem_key": idem_key,
            "world_id": world_id,
            "procedure": procedure,
            "bundle_sha256": bundle_sha256,
            "step": step,
            "scratch": str(scratch),
            "argv_sha256": sha256_bytes(json.dumps(argv, sort_keys=True).encode()),
            "interpreter": interpreter,
            "interpreter_version": version,
            "env_keys": env_keys,
            "input_hashes": input_hashes,
        },
        actor=world_id,
    )
    # P9 excludes this key's WHOLE proc-scratch subtree (all attempts),
    # not just the current attempt: a SIGKILL mid-step can orphan the
    # detached step child (start_new_session, required so the P6
    # timeout-kill cannot take the host), and the orphan may complete
    # its writes into the dead attempt's scratch AFTER the re-run's
    # before-snapshot. Dead-attempt scratch is never content-read
    # (collection/adoption target one live scratch each); the only
    # probes are DONE.json presence checks, which an orphan cannot
    # flip (DONE.json is parent-written after the wait the killed
    # parent never survived). The exclusion stays tight: other keys'
    # scratch, ballast, ledger, artifacts, and worlds are guarded.
    p9_exclude = base / "state" / "proc-scratch" / idem_key
    before = snapshot_state(base, p9_exclude)
    # Spawn (P1 argv-list, P2 cwd, P3 env, P4 devnull stdin, P5 pipes).
    try:
        child = subprocess.Popen(
            argv,
            cwd=str(scratch),
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
            start_new_session=True,
        )
    except OSError as exc:
        proc = _proc_block_base(procedure, bundle_sha256, idem_key, step, attempt)
        # Eager: the except-as target is deleted at block end.
        spawnfail_text = f"spawn failed: {exc}"

        def _spawnfail() -> str:
            raise RuntimeError(spawnfail_text)

        host.invoke(
            world_id,
            world_id,
            PROC_CAP,
            PROC_VER,
            args_ref,
            _spawnfail,
            cost_usd=0.0,
            time_s=0.0,
            extra={"proc": proc},
            invoke_id=invoke_id,
        )
        raise RuntimeError(f"spawn failed: {exc}") from exc
    t0 = time.monotonic()
    try:
        out, err = child.communicate(timeout=timeout)
        timed_out = False
    except subprocess.TimeoutExpired:
        _kill_group(child)  # P6: group SIGKILL, then reap
        out, err = child.communicate()
        timed_out = True
    elapsed = round_up_01(time.monotonic() - t0)
    rc = child.returncode
    out_c, out_tr = _cap_stream(out or b"", STDOUT_CAP)
    err_c, err_tr = _cap_stream(err or b"", STDERR_CAP)
    host_stdio = scratch / HOST_STDIO_DIR
    atomic_write_bytes(host_stdio / STDOUT_NAME, out_c)
    atomic_write_bytes(host_stdio / STDERR_NAME, err_c)
    proc = _proc_block_base(procedure, bundle_sha256, idem_key, step, attempt)
    proc.update(
        {
            "exit_code": rc,
            "stdout_sha256": sha256_bytes(out_c),
            "stdout_bytes": len(out_c),
            "stderr_sha256": sha256_bytes(err_c),
            "stderr_bytes": len(err_c),
            "truncated_stdout": out_tr,
            "truncated_stderr": err_tr,
            "elapsed_s": elapsed,
            "timed_out": timed_out,
        }
    )
    if timed_out:
        failed = base / "artifacts" / f"proc-{idem_key}" / f"{step}-failed-a{attempt}"
        atomic_write_bytes(failed / STDOUT_NAME, out_c)
        atomic_write_bytes(failed / STDERR_NAME, err_c)

        def _timeout() -> str:
            raise TimeoutError(
                f"step {step!r} exceeded timeout_s={timeout} "
                f"(child group killed; partial stdio kept)"
            )

        host.invoke(
            world_id,
            world_id,
            PROC_CAP,
            PROC_VER,
            args_ref,
            _timeout,
            cost_usd=0.0,
            time_s=0.0,
            extra={"proc": proc},
            invoke_id=invoke_id,
        )
        raise TimeoutError(f"step {step!r} timed out after {timeout}s")
    if rc != 0:
        failed = base / "artifacts" / f"proc-{idem_key}" / f"{step}-failed-a{attempt}"
        atomic_write_bytes(failed / STDOUT_NAME, out_c)
        atomic_write_bytes(failed / STDERR_NAME, err_c)

        def _nonzero() -> str:
            raise RuntimeError(
                f"step {step!r} exited {rc} (nonzero ⇒ no result adopted)"
            )

        host.invoke(
            world_id,
            world_id,
            PROC_CAP,
            PROC_VER,
            args_ref,
            _nonzero,
            cost_usd=0.0,
            time_s=0.0,
            extra={"proc": proc},
            invoke_id=invoke_id,
        )
        raise RuntimeError(f"step {step!r} exited {rc}")
    # rc == 0: finalize inside host.invoke so grants consume on
    # success only (P14) and every defect lands an error-invoke.
    dest = base / "artifacts" / f"proc-{idem_key}" / step

    def _finalize() -> str:
        done_artifacts = []
        for rel in declared:
            src = scratch / rel
            if src.is_symlink() or not src.is_file():
                raise ValueError(
                    f"declared output {rel!r} missing (or not a "
                    f"regular file); the child broke its contract"
                )
            done_artifacts.append(_artifact_record(rel, src.read_bytes()))
        done = {
            "exit_code": 0,
            "artifacts": done_artifacts,
            "stdout": {
                "sha256": proc["stdout_sha256"],
                "bytes": proc["stdout_bytes"],
                "truncated": out_tr,
                "total_bytes": len(out or b""),
            },
            "stderr": {
                "sha256": proc["stderr_sha256"],
                "bytes": proc["stderr_bytes"],
                "truncated": err_tr,
                "total_bytes": len(err or b""),
            },
            "elapsed_s": elapsed,
            "at": utcnow(),
        }
        atomic_write_text(
            scratch / DONE_NAME, json.dumps(done, indent=2, sort_keys=True) + "\n"
        )
        maybe_crash_at("proc:post-done-pre-invoke")  # L3, test-only
        try:
            verify_bundle(staged, bundle_sha256)  # P8 post-run
        except ValueError as exc:
            raise ValueError(f"bundle post-verify refused: {exc}") from exc
        diffs = compare_snapshots(before, snapshot_state(base, p9_exclude))
        if diffs:  # P9: outside-scratch writes fail the step
            proc["outside_writes"] = diffs
            raise ValueError(f"outside-scratch writes detected (P9): {diffs}")
        artifacts, undeclared = _collect_declared(scratch, declared, dest)
        atomic_write_bytes(dest / STDOUT_NAME, out_c)
        atomic_write_bytes(dest / STDERR_NAME, err_c)
        proc["artifacts"] = artifacts
        proc["undeclared_present"] = undeclared
        result_ref = str(dest / RESULT_NAME)
        result = dict(proc)
        result.update(
            {
                "invoke_id": invoke_id,
                "stdout_total_bytes": len(out or b""),
                "stderr_total_bytes": len(err or b""),
                "caps": {"stdout": STDOUT_CAP, "stderr": STDERR_CAP},
                "result": "success",
            }
        )
        atomic_write_text(
            result_ref, json.dumps(result, indent=2, sort_keys=True) + "\n"
        )
        return result_ref

    return host.invoke(
        world_id,
        world_id,
        PROC_CAP,
        PROC_VER,
        args_ref,
        _finalize,
        cost_usd=0.0,
        time_s=elapsed,
        extra={"proc": proc},
        invoke_id=invoke_id,
    )


def proc_success_refs(
    host: MiniHost, bundle_sha256: str, idem_key: str
) -> dict[str, str]:
    """{step: result_ref} for success invokes under (bundle, key)."""
    out: dict[str, str] = {}
    for e in host.ledger_entries():
        if e.get("kind") != "invoke":
            continue
        p = e.get("payload", {})
        if p.get("capability") != PROC_CAP or "error" in p or "result_ref" not in p:
            continue
        proc = p.get("proc", {})
        if (
            proc.get("bundle_sha256") == bundle_sha256
            and proc.get("idem_key") == idem_key
            and proc.get("step")
        ):
            out[proc["step"]] = p["result_ref"]
    return out


def _invokes_for_begin(host: MiniHost, invoke_id: str) -> list[dict]:
    return [
        e.get("payload", {})
        for e in host.ledger_entries()
        if e.get("kind") == "invoke"
        and e.get("payload", {}).get("invoke_id") == invoke_id
        and e.get("payload", {}).get("capability") == PROC_CAP
    ]


def run_procedure(
    host: MiniHost,
    root: str | os.PathLike,
    world_id: str,
    procedure: str,
    idem_key: str,
    inputs: dict | None = None,
) -> dict:
    """Execute all steps of a table procedure in order, with skip-match.

    Returns {skipped, executed, re_executed_steps, child_executions,
    results}: skipped steps matched a success invoke (zero spawn);
    executed steps spawned now; re_executed_steps had a prior begin
    (kill re-runs — the carried execute_plan shape: a SUBSET of
    executed); child_executions maps step → total proc_begin count;
    results maps every step → result_ref. A side-complete step
    (DONE, no invoke) raises RuntimeError naming `ops recover`
    (adopt first — never silently re-executed, never silently
    adopted here).
    """
    validate_idem_key(idem_key)
    world = host.worlds.get(world_id)
    if world is None:
        _deny(host, world_id, f"unknown callee {world_id!r}")
        raise ContractViolation(f"unknown callee {world_id!r}")
    entry = table_entry(world, procedure)
    if entry is None:
        reason = (
            f"{world_id!r} procedure table has no procedure "
            f"{procedure!r} (fixed at creation; new content "
            f"needs a new world)"
        )
        _deny(host, world_id, reason, {"procedure": procedure})
        raise ContractViolation(reason)
    bundle = entry.get("bundle_sha256", "")
    priors = proc_prior_bundles(host, idem_key)
    if priors and bundle not in priors:
        reason = (
            f"idempotence key collision across content: key "
            f"{idem_key!r} already recorded bundle(s) "
            f"{sorted(p[:16] for p in priors)}; refusing "
            f"{bundle[:16]}..."
        )
        _deny(host, world_id, reason, {"idem_key": idem_key, "bundle_sha256": bundle})
        raise ValueError(reason)
    succeeded = proc_succeeded(host)
    skipped: list[str] = []
    executed: list[str] = []
    re_executed: list[str] = []
    for step in entry.get("steps", []):
        if (bundle, idem_key, step) in succeeded:
            skipped.append(step)
            continue
        for begin in proc_begins(host, idem_key, step):
            linked = _invokes_for_begin(host, begin.get("invoke_id", ""))
            if linked:
                continue  # failed attempt: re-run allowed below
            done_path = Path(begin.get("scratch", "")) / DONE_NAME
            if done_path.is_file():
                raise RuntimeError(
                    f"step {step!r} is side-complete (DONE present, "
                    f"no invoke): run `ops recover` to adopt, then "
                    f"re-invoke (never silently re-executed)"
                )
        had_begin = bool(proc_begins(host, idem_key, step))
        run_step(host, root, world_id, procedure, bundle, step, idem_key, inputs)
        executed.append(step)
        if had_begin:
            re_executed.append(step)
    child_executions = {
        step: len(proc_begins(host, idem_key, step)) for step in entry.get("steps", [])
    }
    return {
        "skipped": skipped,
        "executed": executed,
        "re_executed_steps": re_executed,
        "child_executions": child_executions,
        "results": proc_success_refs(host, bundle, idem_key),
    }


# ------------------------------------------------- adopt + recovery
#
# L3 adopt-if-complete (§1.7): DONE present + no invoke ⇒ VERIFY
# (DONE + artifact re-hash + stdio re-hash + bundle post-hash all
# MATCH) then ADOPT (atomic result_ref + ONE invoke,
# recovered:true). Recovery NEVER spawns (adopt + report only —
# asserted by construction + runtime tests). Adopt is
# ledger-conditional on BOTH the consume (evidence_ref) and the
# invoke (invoke_id): kill-during-adopt (L5) re-runs converge with
# exactly-once accounting.


class AdoptRefused(Exception):
    """Adopt-path verification mismatch (recorded, then re-run)."""


def scan_proc_partials(host: MiniHost) -> tuple[list[dict], list[dict]]:
    """(adoptable, rerunnable) proc begins. Adoptable = DONE present +
    no linked invoke of any kind. Rerunnable = interrupted mid-step
    (no DONE + no linked invoke). Failed attempts (error invoke
    linked) are caller-retries, not recovery work: excluded."""
    adoptable: list[dict] = []
    rerunnable: list[dict] = []
    succeeded = proc_succeeded(host)
    for e in host.ledger_entries():
        if e.get("kind") != "proc_begin":
            continue
        begin = e.get("payload", {})
        if (
            begin.get("bundle_sha256"),
            begin.get("idem_key"),
            begin.get("step"),
        ) in succeeded:
            continue  # step complete: stale begins are not work
        if _invokes_for_begin(host, begin.get("invoke_id", "")):
            continue
        done_path = Path(begin.get("scratch", "")) / DONE_NAME
        if done_path.is_file():
            adoptable.append(begin)
        else:
            rerunnable.append(begin)
    return adoptable, rerunnable


def adopt_begin(host: MiniHost, root: str | os.PathLike, begin: dict) -> dict:
    """Adopt one L3 begin (verify + ONE recovered invoke).

    Returns the adopt invoke entry. Raises AdoptRefused (after
    recording an error-invoke — the re-run path stays open) on any
    verification mismatch, ContractViolation when adoption is
    impossible (world missing/not active — the settle footgun — or a
    success already recorded for the key+step).
    """
    base = Path(root)
    world_id = begin.get("world_id", "")
    procedure = begin.get("procedure", "")
    bundle = begin.get("bundle_sha256", "")
    key = begin.get("idem_key", "")
    step = begin.get("step", "")
    invoke_id = begin.get("invoke_id", "")
    scratch = Path(begin.get("scratch", ""))
    world = host.worlds.get(world_id)
    if world is None:
        raise ContractViolation(f"adopt refused: world {world_id!r} unknown")
    if world.lifecycle != "active":
        raise ContractViolation(
            f"adopt refused: world {world_id!r} is "
            f"{world.lifecycle} (adoption needs an active world; "
            f"settling a proc world with DONE-pending steps strands "
            f"them — INT-BOUNDARIES §8)"
        )
    if (bundle, key, step) in proc_succeeded(host):
        raise ContractViolation(
            f"adopt refused: step {step!r} already succeeded under "
            f"key {key!r} (refusing a second adopt)"
        )
    if _invokes_for_begin(host, invoke_id):
        raise ContractViolation(
            f"adopt refused: begin {invoke_id} already has a linked "
            f"invoke (nothing to adopt)"
        )
    entry = table_entry(world, procedure)
    if entry is None or entry.get("bundle_sha256") != bundle:
        raise ContractViolation(
            f"adopt refused: ({procedure!r}, bundle "
            f"{bundle[:16]}...) not in the live table"
        )
    staged = Path(world.instance_state_dir) / "procedures" / procedure
    args_ref = _args_ref_for(
        host, world_id, procedure, bundle, key, step, begin.get("input_hashes", {})
    )
    proc = _proc_block_base(procedure, bundle, key, step, 1)
    begins = proc_begins(host, key, step)
    for i, cand in enumerate(begins):
        if cand.get("invoke_id") == invoke_id:
            proc["attempt"] = i + 1
            break

    def _refuse(why: str):
        def _raise() -> str:
            raise AdoptRefused(why)

        host.invoke(
            world_id,
            world_id,
            PROC_CAP,
            PROC_VER,
            args_ref,
            _raise,
            cost_usd=0.0,
            time_s=0.0,
            extra={"proc": proc},
            invoke_id=invoke_id,
        )
        raise AdoptRefused(why)

    done_path = scratch / DONE_NAME
    if not done_path.is_file() or done_path.is_symlink():
        return _refuse(f"DONE {done_path} missing (not adoptable)")
    try:
        done = json.loads(done_path.read_text(encoding="utf-8"))
    except ValueError as exc:
        return _refuse(f"DONE unparseable ({exc})")
    if not isinstance(done, dict) or done.get("exit_code") != 0:
        return _refuse("DONE exit_code != 0 (not adoptable)")
    try:
        manifest = verify_bundle(staged, bundle)
    except ValueError as exc:
        return _refuse(f"bundle post-hash mismatch: {exc}")
    step_def = next((s for s in manifest["steps"] if s.get("step") == step), None)
    if step_def is None:
        return _refuse(f"step {step!r} not in the verified manifest")
    declared = list(step_def["declared_outputs"])
    want = {
        a.get("relpath"): a for a in done.get("artifacts", []) if isinstance(a, dict)
    }
    if set(want) != set(declared):
        return _refuse(
            "DONE artifact set != declared outputs "
            f"({sorted(want)} vs {sorted(declared)})"
        )
    for rel in declared:
        src = scratch / rel
        if src.is_symlink() or not src.is_file():
            return _refuse(f"DONE re-hash: {rel!r} missing/unreadable")
        data = src.read_bytes()
        if sha256_bytes(data) != want[rel].get("sha256") or len(data) != want[rel].get(
            "bytes"
        ):
            return _refuse(f"DONE re-hash: {rel!r} bytes differ")
    for stream, cname in (("stdout", STDOUT_NAME), ("stderr", STDERR_NAME)):
        claim = done.get(stream, {})
        kept = scratch / HOST_STDIO_DIR / cname
        if not kept.is_file() or kept.is_symlink():
            return _refuse(f"host stdio {cname} missing from scratch")
        data = kept.read_bytes()
        if sha256_bytes(data) != claim.get("sha256") or len(data) != claim.get("bytes"):
            return _refuse(f"host stdio {cname} bytes differ from DONE")
    elapsed = done.get("elapsed_s", 0.0)
    if not isinstance(elapsed, (int, float)) or elapsed < 0:
        return _refuse("DONE elapsed_s malformed")
    elapsed = round_up_01(float(elapsed))
    # Verified: collect (idempotent copy) + stdio + RESULT, then the
    # ledger-conditional consume + ONE invoke (recovered:true).
    dest = base / "artifacts" / f"proc-{key}" / step
    try:
        artifacts, undeclared = _collect_declared(scratch, declared, dest)
    except ValueError as exc:
        return _refuse(f"collect at adopt: {exc}")
    out_c = (scratch / HOST_STDIO_DIR / STDOUT_NAME).read_bytes()
    err_c = (scratch / HOST_STDIO_DIR / STDERR_NAME).read_bytes()
    atomic_write_bytes(dest / STDOUT_NAME, out_c)
    atomic_write_bytes(dest / STDERR_NAME, err_c)
    # Truncation flags + totals are carried from DONE (parent-written,
    # atomic: DONE present ⇒ whole). The kept bytes were re-verified
    # above; only the pre-truncation totals are carried unverified.
    out_tr = bool(done.get("stdout", {}).get("truncated", False))
    err_tr = bool(done.get("stderr", {}).get("truncated", False))
    proc.update(
        {
            "exit_code": 0,
            "stdout_sha256": sha256_bytes(out_c),
            "stdout_bytes": len(out_c),
            "stderr_sha256": sha256_bytes(err_c),
            "stderr_bytes": len(err_c),
            "truncated_stdout": out_tr,
            "truncated_stderr": err_tr,
            "artifacts": artifacts,
            "undeclared_present": undeclared,
            "elapsed_s": elapsed,
            "timed_out": False,
            "recovered": True,
        }
    )
    result_ref = str(dest / RESULT_NAME)
    result = dict(proc)
    result.update(
        {
            "invoke_id": invoke_id,
            "stdout_total_bytes": done.get("stdout", {}).get("total_bytes", len(out_c)),
            "stderr_total_bytes": done.get("stderr", {}).get("total_bytes", len(err_c)),
            "caps": {"stdout": STDOUT_CAP, "stderr": STDERR_CAP},
            "result": "success",
        }
    )
    atomic_write_text(result_ref, json.dumps(result, indent=2, sort_keys=True) + "\n")
    already_consumed = any(
        e.get("kind") == "consume"
        and e.get("payload", {}).get("evidence_ref") == invoke_id
        for e in host.ledger_entries()
    )
    try:
        if not already_consumed:
            host.consume(
                world_id,
                cost_usd=0.0,
                time_s=elapsed,
                invocations=1,
                evidence_ref=invoke_id,
            )
    except ContractViolation as exc:
        raise ContractViolation(
            f"adopt refused: grant exhausted ({exc}); terminal — no top-up op exists"
        ) from exc
    if _invokes_for_begin(host, invoke_id):
        return [
            e
            for e in host.ledger_entries()
            if e.get("kind") == "invoke"
            and e.get("payload", {}).get("invoke_id") == invoke_id
            and e.get("payload", {}).get("capability") == PROC_CAP
        ][0]
    return host.append(
        "invoke",
        {
            "invoke_id": invoke_id,
            "caller": world_id,
            "callee": world_id,
            "capability": PROC_CAP,
            "version": PROC_VER,
            "args_ref": args_ref,
            "result_ref": result_ref,
            "cost": {"cost_usd": 0.0, "time_s": elapsed},
            "proc": dict(proc),
        },
        actor=world_id,
    )


def proc_recover(host: MiniHost, root: str | os.PathLike) -> dict:
    """Adopt-if-complete + report re-runnable steps (recovery side).

    Never spawns (adopt + report only). Returns {adopted: [{world,
    step, idem_key, invoke_id, result_ref}...], rerunnable: [{world,
    step, idem_key, reason}...], nothing_to_do: bool}. Adopt-refused
    begins (verification mismatch, error-invoke recorded) are
    reported rerunnable with the refusal as the reason (the re-run
    path); adopt-impossible begins (ContractViolation: settled
    world, second adopt, exhausted grant) are reported rerunnable
    with a terminal reason and NO new ledger effect, so repeated
    recovers are stable and unrelated recovery work is never
    blocked.
    """
    adoptable, rerunnable = scan_proc_partials(host)
    adopted: list[dict] = []
    rerun: list[dict] = []
    for begin in adoptable:
        label = {
            "world": begin.get("world_id", ""),
            "step": begin.get("step", ""),
            "idem_key": begin.get("idem_key", ""),
        }
        try:
            entry = adopt_begin(host, root, begin)
        except AdoptRefused as exc:
            rerun.append(
                dict(label, reason=f"adopt-refused: {exc}; re-invoke to re-run fresh")
            )
        except ContractViolation as exc:
            rerun.append(
                dict(label, reason=f"adopt-impossible (no ledger effect): {exc}")
            )
        else:
            adopted.append(
                dict(
                    label,
                    invoke_id=entry["payload"].get("invoke_id", ""),
                    result_ref=entry["payload"].get("result_ref", ""),
                )
            )
    for begin in rerunnable:
        rerun.append(
            {
                "world": begin.get("world_id", ""),
                "step": begin.get("step", ""),
                "idem_key": begin.get("idem_key", ""),
                "reason": "killed mid-step (no DONE): re-invoke "
                "the same key to re-run fresh",
            }
        )
    rerun.sort(key=lambda d: (d["world"], d["step"], d["idem_key"]))
    adopted.sort(key=lambda d: (d["world"], d["step"], d["idem_key"]))
    return {
        "adopted": adopted,
        "rerunnable": rerun,
        "nothing_to_do": not adopted and not rerun,
    }
