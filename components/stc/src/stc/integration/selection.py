"""Trusted test selection (D-epsilon, section 5.2).

The generated proposal MUST NOT decide its own examination. Affected
coverage is a TRUSTED ORCHESTRATION responsibility, computed
deterministically from candidate bytes through the versioned
owning-suite map; candidate-suggested tests are additive-only input.

- MANDATORY SET (always runs per node): frozen in ONE versioned
  selection-config data file (``selection_config.json``): M1 node
  (env+identity pin), M2 nodes (lease-import integrity), M3 files
  whole (custody shape pins) with per-file node-count tripwire (count
  change = finding). Missing files or node IDs fail closed.
- AFFECTED SET: candidate diff paths/symbols through
  ``owning_suite_map.json`` (map revision bound by the selection
  config) plus declared dependents.
- BROADEN-ON-UNCERTAINTY: any unresolvable path/symbol runs the
  broader scope (owning directory suite minimum; whole Gate-3 class
  maximum). Uncertainty NEVER narrows.
- NAMING RULE: plausibly-affected-but-unrun tests are named in the
  selection record with reasons; an unnamed omission is a receipt defect.
- CANDIDATE-SUGGESTED TESTS: appended with provenance ``suggested``;
  they may ADD coverage and satisfy NOTHING.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

from stc.integration.identity import IntegrationError

__all__ = [
    "SelectionError",
    "SelectionResult",
    "compute_affected_set",
    "is_external_target_root",
    "load_owning_suite_map",
    "load_selection_config",
    "mandatory_set_digest",
    "run_selection",
    "verify_mandatory_set",
]

_CONFIG_NAME: Final[str] = "selection_config.json"
_MAP_NAME: Final[str] = "owning_suite_map.json"
_COLLECT_TIMEOUT_S: Final[int] = 300


def _default_selection_root() -> Path:
    """Default tree for mandatory-set verification (orchestration context).

    The mandatory set is STC-owned definition: existence + node counts
    verify against the STC tree containing this selector (the harness's
    own tree). For STC-tree targets the lease then RUNS those IDs;
    lease-side absence fails the gate red naturally (fail-closed at
    execution). External targets (``run_selection(..., target_root=)``
    outside this tree) verify for provenance but scope the lease gate
    to the target suite instead. An explicit ``workspace`` overrides
    this default.
    """
    return Path(__file__).resolve().parents[3]


def is_external_target_root(target_root: str | Path | None) -> bool:
    """True when ``target_root`` names a tree outside the STC tree.

    Unset/empty roots and the STC tree itself are NOT external (legacy
    behavior). Comparison is on resolved absolute paths so symlinked
    spellings of the STC tree still match. Single definition of
    externality shared by test selection and mutation scoping.
    """
    if not target_root:
        return False
    return Path(target_root).resolve() != _default_selection_root().resolve()


#: In-process tripwire cache: (config path, file sha256s) -> counts.
#: Recomputed whenever file bytes change; deterministic within a session.
_tripwire_cache: dict[tuple[str, ...], dict[str, int]] = {}


class SelectionError(IntegrationError):
    """Trusted selection failure (fail-closed: no verdict without coverage)."""


def _data_path(name: str) -> Path:
    return Path(__file__).resolve().parent / name


def load_selection_config(path: str | Path | None = None) -> dict[str, Any]:
    """Loads the ONE versioned selection-config data file."""
    cfg_path = Path(path) if path is not None else _data_path(_CONFIG_NAME)
    try:
        config = json.loads(cfg_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise SelectionError(f"selection config unreadable: {cfg_path}: {exc}") from exc
    except ValueError as exc:
        raise SelectionError(f"selection config invalid JSON: {cfg_path}: {exc}") from exc
    if not isinstance(config, dict):
        raise SelectionError(f"selection config must be a JSON object: {cfg_path}")
    for key in (
        "config_revision",
        "m1_env_identity_pin",
        "m2_lease_import_integrity",
        "m3_custody_shape_pins",
        "owning_suite_map_revision",
    ):
        if key not in config:
            raise SelectionError(f"selection config missing key: {key}")
    return config


def load_owning_suite_map(
    path: str | Path | None = None, *, required_revision: str | None = None
) -> dict[str, Any]:
    """Loads the versioned owning-suite map; binds the required revision."""
    map_path = Path(path) if path is not None else _data_path(_MAP_NAME)
    try:
        suite_map = json.loads(map_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise SelectionError(f"owning-suite map unreadable: {map_path}: {exc}") from exc
    except ValueError as exc:
        raise SelectionError(f"owning-suite map invalid JSON: {map_path}: {exc}") from exc
    if not isinstance(suite_map, dict):
        raise SelectionError(f"owning-suite map must be a JSON object: {map_path}")
    if required_revision is not None and suite_map.get("map_revision") != required_revision:
        raise SelectionError(
            f"owning-suite map revision {suite_map.get('map_revision')!r} != "
            f"selection-config bound {required_revision!r} (fail-closed)"
        )
    return suite_map


def mandatory_set_digest(config: dict[str, Any]) -> str:
    """Binds the mandatory set (config revision + IDs + paths + counts)."""
    payload = {
        "config_revision": config["config_revision"],
        "m1": sorted(config["m1_env_identity_pin"]),
        "m2": sorted(config["m2_lease_import_integrity"]),
        "m3": sorted(
            (entry["path"], int(entry["node_count"])) for entry in config["m3_custody_shape_pins"]
        ),
        "owning_suite_map_revision": config["owning_suite_map_revision"],
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _collect_node_count(pytest_path: str, workspace: Path) -> int:
    """Counts collected nodes for one file via ``pytest --collect-only -q``.

    Runs with the CURRENT process env (whatever makes imports resolvable
    for orchestration propagates) and cwd at the workspace root so node
    IDs are repo-relative. Any failure fails closed (a count that cannot
    be taken cannot be trusted).
    """
    try:
        proc = subprocess.run(
            [
                sys.executable,
                "-B",
                "-m",
                "pytest",
                "--collect-only",
                "-q",
                "-p",
                "no:cacheprovider",
                pytest_path,
            ],
            cwd=str(workspace),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=_COLLECT_TIMEOUT_S,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SelectionError(f"node-count collect failed for {pytest_path}: {exc}") from exc
    if proc.returncode != 0:
        raise SelectionError(
            f"node-count collect failed for {pytest_path}: "
            f"{(proc.stderr or proc.stdout or '').strip()[-500:]}"
        )
    count = 0
    for line in (proc.stdout or "").splitlines():
        if line.startswith(pytest_path + "::") or line == pytest_path:
            count += 1
    if count == 0:
        # Fall back to the summary line ("N tests collected") when -q
        # prints only the tally (robust across pytest 8.x/9.x output).
        match = re.search(r"(\d+) tests? collected", proc.stdout or "")
        if match:
            return int(match.group(1))
        raise SelectionError(f"node-count collect parsed 0 nodes for {pytest_path}")
    return count


def verify_mandatory_set(
    config: dict[str, Any], *, workspace: str | Path | None = None
) -> dict[str, Any]:
    """Verifies mandatory files exist + node-count tripwire (fail-closed).

    Every M1/M2 node file and M3 file must exist (missing fails closed);
    every M3 per-file live count must equal the pinned count (count
    change = finding, failed closed). Returns the verification record
    (provenance + live counts) for the SelectionRecord.
    """
    ws = Path(workspace) if workspace is not None else _default_selection_root()
    node_ids = list(config["m1_env_identity_pin"]) + list(config["m2_lease_import_integrity"])
    for node_id in node_ids:
        if "::" not in node_id:
            raise SelectionError(f"mandatory node id malformed: {node_id}")
        node_file = ws / node_id.split("::", 1)[0]
        if not node_file.is_file():
            raise SelectionError(f"mandatory node file missing (fail-closed): {node_id}")
    live_counts: dict[str, int] = {}
    file_shas: list[str] = []
    for entry in config["m3_custody_shape_pins"]:
        rel = str(entry["path"])
        target = ws / rel
        if not target.is_file():
            raise SelectionError(f"mandatory M3 file missing (fail-closed): {rel}")
        try:
            file_shas.append(hashlib.sha256(target.read_bytes()).hexdigest())
        except OSError as exc:
            raise SelectionError(f"mandatory M3 file unreadable: {rel}: {exc}") from exc
    cache_key = (str(_data_path(_CONFIG_NAME)), *file_shas)
    cached = _tripwire_cache.get(cache_key)
    if cached is not None:
        live_counts.update(cached)
    else:
        fresh: dict[str, int] = {}
        for entry in config["m3_custody_shape_pins"]:
            rel = str(entry["path"])
            fresh[rel] = _collect_node_count(rel, ws)
        _tripwire_cache[cache_key] = fresh
        live_counts.update(fresh)
    for entry in config["m3_custody_shape_pins"]:
        rel = str(entry["path"])
        pinned = int(entry["node_count"])
        if live_counts[rel] != pinned:
            raise SelectionError(
                f"node-count tripwire: {rel} collects {live_counts[rel]} nodes, "
                f"config pins {pinned} (count change = finding; fail-closed)"
            )
    return {
        "config_revision": config["config_revision"],
        "mandatory_digest": mandatory_set_digest(config),
        "workspace": str(ws),
        "m3_live_counts": live_counts,
    }


@dataclass
class SelectionResult:
    """Deterministic trusted-selection outcome for one candidate."""

    pytest_target: str
    mandatory: list[str] = field(default_factory=list)
    affected: list[str] = field(default_factory=list)
    broadenings: list[str] = field(default_factory=list)
    unrun_with_reasons: list[dict[str, str]] = field(default_factory=list)
    suggested: list[str] = field(default_factory=list)


def _convention_target(diff_path: str, workspace: Path) -> str | None:
    """Naming-convention fallback: ``src/stc/<area>/<mod>.py`` target.

    Returns the conventional test file when it exists, else None (the
    caller broadens). ``tests/**`` paths map to themselves.
    """
    if diff_path.startswith("tests/"):
        candidate = workspace / diff_path
        return diff_path if candidate.is_file() else None
    parts = diff_path.split("/")
    if len(parts) >= 4 and parts[0] == "src" and parts[1] == "stc" and diff_path.endswith(".py"):
        conventional = f"tests/unit/test_{parts[-1][:-3]}.py"
        # Strip a redundant test_ prefix (test_config.py, not test_test_config.py).
        conventional = conventional.replace("test_test_", "test_")
        if (workspace / conventional).is_file():
            return conventional
    return None


def compute_affected_set(
    diff_paths: list[str],
    symbols: list[str],
    suite_map: dict[str, Any],
    *,
    workspace: str | Path | None = None,
) -> SelectionResult:
    """Minimal deterministic affected-set computation (section 5.2).

    Exact map hit -> owning tests; else tests-self/convention; else
    broaden (owning directory suite minimum; whole Gate-3 class —
    i.e. no narrowing target — maximum). Symbols resolve through
    declared dependents, else broaden. Deterministic: sorted, stable.
    """
    ws = Path(workspace) if workspace is not None else _default_selection_root()
    path_map = suite_map.get("path_map", {})
    symbol_deps = suite_map.get("symbol_dependents", {})
    affected: set[str] = set()
    broadenings: set[str] = set()
    unrun: list[dict[str, str]] = []
    for raw in sorted(set(diff_paths)):
        rel = raw.strip().lstrip("/").replace("\\", "/")
        if not rel:
            continue
        if rel in path_map:
            for target in path_map[rel]:
                if (ws / target).is_file():
                    affected.add(target)
                else:
                    unrun.append({"test": target, "reason": f"map hit for {rel} but file absent"})
            continue
        conventional = _convention_target(rel, ws)
        if conventional is not None:
            affected.add(conventional)
            continue
        parent = "/".join(rel.split("/")[:-1])
        if parent and (ws / parent).is_dir():
            broadenings.add(parent)
        else:
            broadenings.add("")  # whole Gate-3 class (no narrowing)
    for symbol in sorted(set(symbols)):
        if symbol in symbol_deps:
            for target in symbol_deps[symbol]:
                if (ws / target).is_file():
                    affected.add(target)
                else:
                    unrun.append({"test": symbol, "reason": f"dependent {target} absent"})
        else:
            broadenings.add("")  # unresolvable symbol: whole class
    return SelectionResult(
        pytest_target="",
        affected=sorted(affected),
        broadenings=sorted(broadenings),
        unrun_with_reasons=sorted(unrun, key=lambda item: item["test"]),
    )


def _external_targets(
    result: SelectionResult,
    mandatory: list[str],
    suggested_tests: list[str],
    troot: Path,
    verification: dict[str, Any],
) -> tuple[SelectionResult, dict[str, Any]]:
    """Builds lease-gate targets for a non-STC target tree.

    The STC mandatory IDs are verified (provenance) but unrunnable in a
    foreign lease, so they are recorded in ``unrun_with_reasons`` and the
    gate runs the TARGET tree's full suite instead: ``tests`` when that
    directory exists, else the whole tree (``.``). Narrowing targets
    already covered by the floor are dropped (redundant, not omitted:
    ``affected``/``broadenings`` still record them). Deterministic:
    floor first, then uncovered narrowings, broadenings, suggested.
    """
    floor = "tests" if (troot / "tests").is_dir() else "."
    targets: list[str] = [floor]
    if floor == "tests":
        for hit in result.affected:
            if hit not in mandatory and not hit.startswith("tests/"):
                targets.append(hit)
        targets.extend(b for b in result.broadenings if b and not b.startswith("tests/"))
    # Floor ".": the whole tree covers every narrowing target already.
    suggested = sorted(set(suggested_tests))
    result.suggested = suggested
    targets.extend(suggested)
    for mid in mandatory:
        result.unrun_with_reasons.append(
            {
                "test": mid,
                "reason": (
                    "external target: STC mandatory set verified but not "
                    "runnable in lease; target suite runs instead"
                ),
            }
        )
    result.unrun_with_reasons.sort(key=lambda item: item["test"])
    seen: set[str] = set()
    ordered: list[str] = []
    for target in targets:
        if target not in seen:
            seen.add(target)
            ordered.append(target)
    result.pytest_target = " ".join(ordered)
    return result, verification


def run_selection(
    diff_paths: list[str],
    symbols: list[str],
    suggested_tests: list[str],
    *,
    workspace: str | Path | None = None,
    config: dict[str, Any] | None = None,
    suite_map: dict[str, Any] | None = None,
    target_root: str | Path | None = None,
) -> tuple[SelectionResult, dict[str, Any]]:
    """Runs the full trusted selection: mandatory + affected + broadenings.

    Returns ``(result, verification_record)``. Whole-class broadening
    (``""`` marker) drops NARROWING targets but the mandatory set still
    runs and is still named. Suggested tests are appended additively and
    satisfy nothing (recorded separately with ``suggested`` provenance).

    External targets (``target_root`` resolves outside the STC tree, e.g.
    a csvledger construction lease) cannot RUN STC's mandatory IDs: the
    files are absent from the lease, so naming them fails every gate red
    regardless of candidate quality. In external mode the mandatory set
    is still VERIFIED against the STC tree (provenance; the tripwire
    still guards harness identity) but the lease gate is scoped to the
    TARGET tree's full suite instead: floor ``tests`` when that directory
    exists, else the whole tree ``.``. Skipped mandatory IDs are recorded
    in ``unrun_with_reasons`` with an explicit reason (naming rule: no
    unnamed omissions). STC-tree targets (``target_root`` unset or equal
    to the STC root) keep the exact legacy behavior.
    """
    cfg = config if config is not None else load_selection_config()
    smap = (
        suite_map
        if suite_map is not None
        else load_owning_suite_map(required_revision=cfg["owning_suite_map_revision"])
    )
    if suite_map is not None and smap.get("map_revision") != cfg["owning_suite_map_revision"]:
        raise SelectionError(
            f"owning-suite map revision {smap.get('map_revision')!r} != "
            f"selection-config bound {cfg['owning_suite_map_revision']!r} (fail-closed)"
        )
    troot = Path(target_root).resolve() if target_root else None
    external = is_external_target_root(target_root)
    verification = verify_mandatory_set(cfg, workspace=workspace)
    result = compute_affected_set(
        diff_paths, symbols, smap, workspace=troot if external else workspace
    )
    mandatory = (
        list(cfg["m1_env_identity_pin"])
        + list(cfg["m2_lease_import_integrity"])
        + [str(entry["path"]) for entry in cfg["m3_custody_shape_pins"]]
    )
    result.mandatory = mandatory
    if external:
        assert troot is not None  # narrowed by `external` above
        return _external_targets(result, mandatory, suggested_tests, troot, verification)
    whole_class = "" in result.broadenings
    narrow = [t for t in result.affected if t not in mandatory]
    directory_broad = sorted(b for b in result.broadenings if b)
    targets: list[str] = list(mandatory)
    if not whole_class:
        targets.extend(narrow)
        targets.extend(directory_broad)
    suggested = sorted(set(suggested_tests))
    result.suggested = suggested
    targets.extend(suggested)
    # De-duplicate, order-stable (mandatory first, then affected,
    # broadenings, suggested).
    seen: set[str] = set()
    ordered: list[str] = []
    for target in targets:
        if target not in seen:
            seen.add(target)
            ordered.append(target)
    result.pytest_target = " ".join(ordered)
    return result, verification
