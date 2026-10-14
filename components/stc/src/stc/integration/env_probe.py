"""Authoritative-environment fingerprint + floor check (D-alpha, section 5.5).

Every candidate check records its EXACT environment fingerprint
(``env_digest``): the exact ``sys.version`` string, the
``ruff``/``mypy``/``pytest``/``mutmut`` ``--version`` strings, the
``uv.lock`` content sha256, and ``os_platform``. Patch drift is a
different fingerprint, recorded always, never a silent same.

Compatibility, provenance, and reuse are DISTINCT and must never be
conflated (ratified section 5.5):

- COMPATIBILITY (floor): Python >= 3.12 with all four gate tools +
  app deps present. Fail closed ONLY on floor violation or missing
  tool (:func:`check_floor`).
- PROVENANCE (fingerprint): :func:`collect_env_fingerprint` records
  the exact strings; :func:`env_digest_of` binds them into one sha256.
- REUSE (requalification): :func:`env_requalifies` — same
  (major, minor) + same tools-present set + same lockfile content
  hash requalifies the ENV side; reuse ALSO requires the full T0 key
  match. The lockfile content hash is necessary, NEVER sufficient by
  itself.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import platform
import shutil
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final

from stc.integration.identity import IntegrationError

__all__ = [
    "APP_DEPS",
    "FLOOR_MAJOR",
    "FLOOR_MINOR",
    "GATE_TOOLS",
    "FloorViolationError",
    "check_floor",
    "collect_env_fingerprint",
    "env_digest_of",
    "env_requalifies",
]

#: Compatibility floor: Python >= 3.12 (rule text; N4 polarity test pins it).
FLOOR_MAJOR: Final[int] = 3
FLOOR_MINOR: Final[int] = 12

#: The four gate tools every authoritative env must carry.
GATE_TOOLS: Final[tuple[str, ...]] = ("ruff", "mypy", "pytest", "mutmut")

#: App dependencies (``[project] dependencies``) that must be installed.
#: Maps distribution name -> importable module name for presence probing.
APP_DEPS: Final[dict[str, str]] = {
    "click": "click",
    "httpx": "httpx",
    "pydantic": "pydantic",
    "pydantic-settings": "pydantic_settings",
    "python-dotenv": "dotenv",
    "pyyaml": "yaml",
    "rich": "rich",
    "tenacity": "tenacity",
}

_TOOL_TIMEOUT_S: Final[int] = 30


class FloorViolationError(IntegrationError):
    """The environment violates the section 5.5 floor (fail-closed)."""


def _tool_version(tool: str) -> str:
    """Probes ``<tool> --version`` bound to the current interpreter first.

    ``sys.executable -m <tool> --version`` binds provenance to the actual
    interpreter; a PATH binary is the fallback. Either exact stdout string
    is recorded. Failure on both yields an honest ``UNAVAILABLE:`` marker
    (which fails the floor check — a missing tool fails closed).
    """
    candidates = [
        [sys.executable, "-m", tool, "--version"],
        [tool, "--version"],
    ]
    for argv in candidates:
        if argv[0] != sys.executable and shutil.which(argv[0]) is None:
            continue
        try:
            proc = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
                timeout=_TOOL_TIMEOUT_S,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        if proc.returncode == 0 and (proc.stdout or "").strip():
            return (proc.stdout or "").strip().splitlines()[0][:300]
    return "UNAVAILABLE:not-resolvable"


def _uv_lock_sha256() -> str:
    """Content sha256 of the STC ``uv.lock`` (dependency-intent provenance).

    A missing lockfile is recorded honestly and does NOT fail the floor:
    the floor is interpreter + tools + app deps only. Reuse comparisons
    treat ``UNAVAILABLE`` as never-equal (requalification fails closed).
    """
    lock = Path(__file__).resolve().parents[3] / "uv.lock"
    try:
        return hashlib.sha256(lock.read_bytes()).hexdigest()
    except OSError:
        return "UNAVAILABLE:no-uv.lock"


def _app_dep_presence() -> dict[str, bool]:
    return {dist: importlib.util.find_spec(mod) is not None for dist, mod in APP_DEPS.items()}


def collect_env_fingerprint() -> dict[str, Any]:
    """Collects the exact per-check environment fingerprint (section 5.5).

    Keys: ``python_version`` (exact ``sys.version`` string),
    ``python_major_minor`` (int pair, derived, for requalification),
    ``tool_versions`` (exact ``--version`` strings per gate tool),
    ``tools_present`` (bool per gate tool), ``uv_lock_sha256``,
    ``app_deps_present`` (bool per distribution), ``os_platform``.
    Pure collection: never raises for missing tools (records markers);
    enforcement is :func:`check_floor`'s job.
    """
    tool_versions = {tool: _tool_version(tool) for tool in GATE_TOOLS}
    return {
        "python_version": sys.version,
        "python_major_minor": [sys.version_info.major, sys.version_info.minor],
        "tool_versions": tool_versions,
        "tools_present": {
            tool: not text.startswith("UNAVAILABLE:") for tool, text in tool_versions.items()
        },
        "uv_lock_sha256": _uv_lock_sha256(),
        "app_deps_present": _app_dep_presence(),
        "os_platform": platform.system(),
    }


def env_digest_of(fingerprint: Mapping[str, Any] | dict[str, Any]) -> str:
    """Binds a fingerprint into one sha256 (canonical JSON, sorted keys)."""
    canonical = json.dumps(dict(fingerprint), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def check_floor(fingerprint: dict[str, Any] | None = None) -> dict[str, Any]:
    """Enforces the section 5.5 floor; fails closed ONLY here-specified.

    Raises :class:`FloorViolationError` iff the interpreter is below
    (3, 12), any of the four gate tools is missing, or any app
    dependency is missing. Patch drift, version-string surprises, and a
    missing ``uv.lock`` NEVER fail here (provenance, not compatibility).
    Returns the (collected or passed) fingerprint for binding.
    """
    fp = fingerprint if fingerprint is not None else collect_env_fingerprint()
    major, minor = int(fp["python_major_minor"][0]), int(fp["python_major_minor"][1])
    if (major, minor) < (FLOOR_MAJOR, FLOOR_MINOR):
        raise FloorViolationError(
            f"floor violation: interpreter {major}.{minor} below "
            f"{FLOOR_MAJOR}.{FLOOR_MINOR} (section 5.5 floor)"
        )
    missing_tools = [tool for tool in GATE_TOOLS if not fp["tools_present"].get(tool, False)]
    if missing_tools:
        raise FloorViolationError(
            f"missing gate tool(s): {', '.join(sorted(missing_tools))} "
            "(section 5.5 floor fails closed on missing tools)"
        )
    missing_deps = sorted(dist for dist, ok in fp["app_deps_present"].items() if not ok)
    if missing_deps:
        raise FloorViolationError(
            f"missing app dep(s): {', '.join(missing_deps)} "
            "(section 5.5 floor fails closed on missing tools)"
        )
    return fp


def env_requalifies(baseline_fp: dict[str, Any], current_fp: dict[str, Any]) -> bool:
    """ENV-side requalification (section 5.5 REUSE): same (major, minor) +
    same tools-present set + same lockfile content hash.

    Tool VERSION strings are provenance (recorded, compared nowhere
    here); tool PRESENCE is what requalifies. ``UNAVAILABLE`` lockfile
    hashes never equal (fail closed). A ``True`` result requalifies the
    ENV side only — reuse ALSO requires the full T0 key match.
    """
    base_mm = list(baseline_fp.get("python_major_minor", []))
    cur_mm = list(current_fp.get("python_major_minor", []))
    if base_mm != cur_mm:
        return False
    if dict(baseline_fp.get("tools_present", {})) != dict(current_fp.get("tools_present", {})):
        return False
    base_lock = baseline_fp.get("uv_lock_sha256", "")
    cur_lock = current_fp.get("uv_lock_sha256", "")
    if not base_lock or not cur_lock:
        return False
    if str(base_lock).startswith("UNAVAILABLE:") or str(cur_lock).startswith("UNAVAILABLE:"):
        return False
    return bool(base_lock == cur_lock)
