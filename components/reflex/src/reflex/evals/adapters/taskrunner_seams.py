"""TaskRunner integration seams (benchmark GAPS#1 / LAUNCH-PLAN G2).

Implements the five seam Protocols defined by the benchmark harness
(``harness/taskrunner.py``: ``PerceptionAdapter``, ``PlannerAdapter``,
``KernelPort``, ``SourcePort``, ``ChannelDriver``) against product surfaces.
This module is benchmark-owned glue: it adapts, never reimplements.

Binding constraints (SEAMS-SCOPE-PROPOSAL.md section A):
- Tracking bundle (``reflex.perception.tracking``) is consumed READ-ONLY
  (``from_dict`` / pure helpers only; no writes, no re-binding).
- Kernel dispatch goes ONLY through ``HostControlKernel.submit_proposal``.
  This module never touches an action adapter directly.
- No benchmark/evaluator-only values (predicates, channel reads, oracle
  internals) may appear in agent-visible ``agent_input`` (P10).

The benchmark harness is intentionally NOT imported here, so this module
stays usable offline: the refusal exception type and the channel
read/assemble functions are injectable at the integration boundary.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import hashlib
import importlib.util
import struct
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from reflex.host.kernel.host_kernel import DispatchState, HostControlKernel
from reflex.perception.tracking.adapters import static_parse_to_node_dicts
from reflex.perception.tracking.frame import (
    FrameIdentity,
    FrameQuality,
    Unsupported,
    ViewportGeometry,
)
from reflex.perception.tracking.interfaces import StaticParse
from reflex.schemas.actions import TypedAction
from reflex.schemas.identity import ActionIdentity, ActionProposal
from reflex.schemas.state import CanonicalUIGraph

__all__ = [
    "AuthorityNotGranted",
    "BaselinePerceptionAdapter",
    "TrackingPerceptionAdapter",
    "build_perception_arms",
    "PlannerAdapter",
    "map_planned_step",
    "HostKernelPort",
    "FrameBoundSourcePort",
    "EvalChannelDriver",
    "load_benchmark_channel_driver",
    "SEAM_REVISION",
]

SEAM_REVISION = "taskrunner-seams/1"


class AuthorityNotGranted(Exception):
    """Local refusal signal: no input dispatch without the P11 authority gate.

    Integration note: the benchmark runner catches the harness's own
    ``AuthorityNotGranted``. Pass that class as ``authority_error`` to
    :class:`HostKernelPort` at integration time so refusals surface as the
    runner's ``CANCELLED``/``authority-refused`` path instead of ``API_ERROR``.
    """


def _run_sync(coro):  # type: ignore[no-untyped-def]
    """Drive one coroutine to completion from sync seam code."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


# --------------------------------------------------------------------------
# Perception adapters (arms A/B/C/D)
# --------------------------------------------------------------------------

def _compact_history(history: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    compact: List[Dict[str, Any]] = []
    for entry in history or []:
        if not isinstance(entry, dict):
            continue
        decision = entry.get("decision", {})
        kind = decision.get("kind", "") if isinstance(decision, dict) else ""
        compact.append(
            {
                "input_digest": str(entry.get("input_digest", "")),
                "kind": str(kind),
            }
        )
    return compact


def _base_agent_input(
    arm: str, observation: Dict[str, Any], history: List[Dict[str, Any]]
) -> Dict[str, Any]:
    frame = observation.get("frame", {}) if isinstance(observation, dict) else {}
    return {
        "arm": arm,
        "task_goal": str(observation.get("task_goal", "")),
        "frame_uid": str(frame.get("uid", "")),
        "pixel_sha256": observation.get("pixel_sha256"),
        "geometry": dict(observation.get("geometry", {})),
        "graph": dict(observation.get("graph", {})),
        "history": _compact_history(history),
    }


class BaselinePerceptionAdapter:
    """Arm A: baseline agent input over the CDP graph only (no tracking)."""

    arm = "A"

    def agent_input(
        self, observation: Dict[str, Any], history: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        return _base_agent_input("A", observation, history)


class TrackingPerceptionAdapter:
    """Arms B/C/D: read-only consumption layer over the tracking bundle.

    Levels (increasing richness, all frame-bound to the same observation):
    - ``B``: region proposals only.
    - ``C``: regions + OCR spans.
    - ``D``: full static parse (regions + OCR + hypotheses + layout) plus
      builder-UIStateNode-shaped dicts via ``static_parse_to_node_dicts``.

    The observation must carry ``static_parse`` (a ``StaticParse.to_dict()``
    payload); when absent the adapter reports ``tracking.status == "not_run"``
    instead of inventing evidence.
    """

    def __init__(self, arm: str = "D") -> None:
        if arm not in ("B", "C", "D"):
            raise ValueError(f"tracking adapter arm must be B, C, or D, got {arm!r}")
        self.arm = arm

    def agent_input(
        self, observation: Dict[str, Any], history: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        payload = _base_agent_input(self.arm, observation, history)
        raw = observation.get("static_parse")
        if raw is None:
            payload["tracking"] = {
                "status": "not_run",
                "frame_uid": payload["frame_uid"],
                "reason": "observation carries no static_parse",
            }
            return payload
        parse = StaticParse.from_dict(raw)
        tracking: Dict[str, Any] = {
            "status": "ok",
            "frame_uid": parse.frame.uid,
            "bound": parse.frame.uid == payload["frame_uid"],
            "component_states": {
                k: v.value for k, v in parse.component_states.items()
            },
            "regions": [r.to_dict() for r in parse.regions],
        }
        if self.arm in ("C", "D"):
            tracking["ocr"] = [o.to_dict() for o in parse.ocr]
        if self.arm == "D":
            tracking["hypotheses"] = [h.to_dict() for h in parse.hypotheses]
            tracking["layout"] = parse.layout.to_dict() if parse.layout else None
            nodes, unsupported = static_parse_to_node_dicts(parse)
            tracking["nodes"] = nodes
            tracking["unsupported"] = [u.to_dict() for u in unsupported]
            tracking["unsupported"] += [u.to_dict() for u in parse.unsupported]
        payload["tracking"] = tracking
        return payload


def build_perception_arms() -> Dict[str, Any]:
    """Return the ``{"A": ..., "B": ..., "C": ..., "D": ...}`` arm mapping."""
    return {
        "A": BaselinePerceptionAdapter(),
        "B": TrackingPerceptionAdapter("B"),
        "C": TrackingPerceptionAdapter("C"),
        "D": TrackingPerceptionAdapter("D"),
    }


# --------------------------------------------------------------------------
# Planner adapter
# --------------------------------------------------------------------------

def map_planned_step(planned: Any) -> Dict[str, Any]:
    """Map one ``PlannedStep`` to exactly one runner decision.

    Mapping table (first match wins):
    1. ``action.metadata["terminal"] == "done"`` -> ``{"kind": "done"}``.
    2. ``action.metadata["terminal"] == "give_up"`` ->
       ``{"kind": "give_up", "reason": ...}``.
    3. Otherwise -> ``{"kind": "act", "action": <TypedAction dict>}``; the
       action dict is round-trip validated through ``TypedAction.from_dict``.
    """
    action_dict = planned.action.to_dict()
    TypedAction.from_dict(action_dict)
    terminal = planned.action.metadata.get("terminal", "")
    if terminal == "done":
        return {"kind": "done"}
    if terminal == "give_up":
        reason = (
            planned.action.metadata.get("give_up_reason")
            or planned.thought_reasoning
            or "planner gave up"
        )
        return {"kind": "give_up", "reason": str(reason)}
    return {"kind": "act", "action": action_dict}


class PlannerAdapter:
    """Sync ``step(agent_input)`` bridge over an async System 2 planner.

    Wraps any planner exposing ``async plan_next_step(task_goal,
    CanonicalUIGraph, history)`` (``System2Planner``,
    ``DeterministicRulePlanner``, or a fixed stub). Planner exceptions
    propagate so the runner records ``MODEL_UNAVAILABLE``.
    """

    def __init__(
        self,
        planner: Any,
        *,
        task_goal: str = "",
        identity: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._planner = planner
        self._task_goal = task_goal
        self.identity: Dict[str, Any] = dict(identity) if identity else {
            "planner": type(planner).__name__,
            "adapter": SEAM_REVISION,
        }

    def step(self, agent_input: Dict[str, Any]) -> Dict[str, Any]:
        goal = str(agent_input.get("task_goal", "") or self._task_goal)
        graph = CanonicalUIGraph.from_dict(agent_input.get("graph", {}))
        history = agent_input.get("history", [])
        planned = _run_sync(
            self._planner.plan_next_step(goal, graph, history)
        )
        return map_planned_step(planned)


# --------------------------------------------------------------------------
# Kernel port (sole dispatch route: HostControlKernel.submit_proposal)
# --------------------------------------------------------------------------

class HostKernelPort:
    """Sync ``dispatch(action_dict)`` over ``HostControlKernel``.

    - Granted authority: returns the kernel result dict and records exactly
      one event per dispatch in :attr:`events`.
    - Refused authority (policy rejection / confirmation denial, i.e. the
      kernel retired the proposal with NO receipt because no physical
      dispatch occurred): raises the configured authority error with
      EXACTLY 0 events recorded.
    - Other kernel failures (settlement/verification) carry a receipt and
      are returned, not raised.
    """

    def __init__(
        self,
        kernel: HostControlKernel,
        *,
        session_id: str = "taskrunner",
        authority_error: Optional[type] = None,
    ) -> None:
        self._kernel = kernel
        self._session_id = session_id
        self._authority_error = authority_error or AuthorityNotGranted
        self._step_index = 0
        self.events: List[Dict[str, Any]] = []

    def dispatch(self, action: Dict[str, Any]) -> Dict[str, Any]:
        typed = TypedAction.from_dict(dict(action))
        identity = ActionIdentity.create(
            session_id=self._session_id, step_index=self._step_index
        )
        self._step_index += 1
        proposal = ActionProposal(
            identity=identity,
            action=typed,
            required_scopes=set(),
            reasoning_summary="taskrunner-seam dispatch",
            metadata={"seam": SEAM_REVISION},
        )
        result = _run_sync(self._kernel.submit_proposal(proposal))
        if result.receipt is None and result.state == DispatchState.RETIRED_FAILED:
            raise self._authority_error(
                result.error_message or "input dispatch refused: no authority"
            )
        self.events.append(
            {
                "event": "dispatched",
                "action_id": identity.action_id,
                "state": result.state.value,
                "verification_passed": result.verification_passed,
            }
        )
        return result.to_dict()


# --------------------------------------------------------------------------
# Source port (frame-bound observation bundle)
# --------------------------------------------------------------------------

def _png_dimensions(pixels: bytes) -> Optional[tuple]:
    """Decode PNG IHDR dimensions from raw bytes (no defaulting)."""
    if len(pixels) < 33 or pixels[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    try:
        (length, ctype) = struct.unpack(">I4s", pixels[8:16])
    except struct.error:
        return None
    if ctype != b"IHDR" or length != 13:
        return None
    width, height = struct.unpack(">II", pixels[16:24])
    if width <= 0 or height <= 0 or width > 16384 or height > 16384:
        return None
    return (width, height)


class FrameBoundSourcePort:
    """Bundle ``capture_state`` + ``capture_screenshot`` + settlement state.

    Joins a CDP observation provider (``CDPObservationProvider`` or the
    ``observation_provider`` of a ``ManagedChromiumSession``) with an
    optional ``SettlementObserver`` snapshot into one frame-bound bundle::

        {"frame": FrameIdentity dict (with uid),
         "frame_uid": str, "pixel_sha256": str, "geometry": ViewportGeometry dict,
         "graph": CanonicalUIGraph dict, "screenshot_len": int,
         "settlement": {...}, "unsupported": [...], "source_id": str}

    Unknown DPR/geometry is reported via ``Unsupported`` entries, never
    defaulted.
    """

    def __init__(
        self,
        provider: Any = None,
        *,
        settlement: Any = None,
        session: Any = None,
        source_id: str = "cdp_chromium/linux",
        document_epoch: str = "",
    ) -> None:
        if provider is None and session is not None:
            provider = getattr(session, "observation_provider", None)
        if provider is None:
            raise ValueError(
                "FrameBoundSourcePort requires a provider or a session "
                "with observation_provider"
            )
        self._provider = provider
        self._settlement = settlement
        self._source_id = source_id
        self._document_epoch = document_epoch
        self._frame_seq = 0

    def observe(self) -> Dict[str, Any]:
        return _run_sync(self._observe_async())

    async def _observe_async(self) -> Dict[str, Any]:
        graph_raw = await self._provider.capture_state()
        if isinstance(graph_raw, dict):
            graph = CanonicalUIGraph.from_dict(graph_raw)
        else:
            graph = graph_raw
        pixels = await self._provider.capture_screenshot()
        digest = hashlib.sha256(bytes(pixels)).hexdigest()

        unsupported: List[Unsupported] = []
        dims = _png_dimensions(bytes(pixels))
        if dims is None:
            unsupported.append(
                Unsupported(
                    feature="pixel_dimensions",
                    reason="screenshot bytes are not a decodable PNG; "
                    "falling back to graph viewport size",
                    needed_by="FrameBoundSourcePort",
                )
            )
            width, height = graph.viewport_size
        else:
            width, height = dims
        unsupported.append(
            Unsupported(
                feature="dpr",
                reason="DPR not reported by the CDP capture path; "
                "refusing to assume 1.0",
                needed_by="FrameBoundSourcePort",
            )
        )
        geometry = ViewportGeometry(width_px=width, height_px=height, dpr=None)

        self._frame_seq += 1
        frame = FrameIdentity(
            source_id=self._source_id,
            frame_id=f"f{self._frame_seq:06d}-{digest[:12]}",
            pixel_sha256=digest,
            geometry=geometry,
            quality=FrameQuality.HEALTHY,
            received_ms=time.time() * 1000.0,
            surface_epoch=str(
                getattr(self._provider, "session_epoch", "") or ""
            ),
            document_epoch=self._document_epoch,
        )
        for entry in unsupported:
            object.__setattr__(entry, "frame_uid", frame.uid)

        if self._settlement is None:
            settlement: Dict[str, Any] = {
                "settled": None,
                "reason": "no settlement observer bound",
            }
        else:
            obs = self._settlement
            settlement = {
                "settled": bool(obs.is_settled()),
                "in_flight": int(obs.in_flight_request_count),
                "mutations": int(obs.mutations_count),
                "animations": int(obs.running_animations_count),
                "page_loaded": bool(obs.is_page_loaded),
            }
        return {
            "frame": frame.to_dict(),
            "frame_uid": frame.uid,
            "pixel_sha256": digest,
            "geometry": geometry.to_dict(),
            "graph": graph.to_dict(),
            "screenshot_len": len(bytes(pixels)),
            "settlement": settlement,
            "unsupported": [u.to_dict() for u in unsupported],
            "source_id": self._source_id,
        }


# --------------------------------------------------------------------------
# Channel driver wiring (evaluator-owned separate read)
# --------------------------------------------------------------------------

def load_benchmark_channel_driver(scripts_path: Any) -> Any:
    """Load benchmark-owned pinned reads + assembly without importing it.

    ``scripts_path`` is either the benchmark ``scripts/`` directory or the
    ``channel_driver.py`` file itself. Returns ``(READS, assemble)``.
    """
    path = Path(scripts_path)
    if path.is_dir():
        path = path / "channel_driver.py"
    spec = importlib.util.spec_from_file_location(
        "bench_channel_driver", str(path)
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load channel driver from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return dict(module.READS), module.assemble


class EvalChannelDriver:
    """Thin ``acquire()`` wiring over pinned benchmark reads + assembly.

    - ``reads_spec`` / ``assemble_fn`` come from
      :func:`load_benchmark_channel_driver` (benchmark-owned,
      reused as-is).
    - ``read_fn(oracle_id, specs, task, attempt_dir)`` is the
      evaluator-owned CDP attach, bound in the trial env; offline it is
      ``None`` and channel-backed acquires raise honestly instead of
      improvising reads.
    - Oracles with no pinned reads (disk-backed) return ``None``.
    """

    def __init__(
        self,
        *,
        reads_spec: Dict[str, Any],
        assemble_fn: Callable[..., Dict[str, Any]],
        read_fn: Optional[Callable[..., Dict[str, Any]]] = None,
        via: str = "evaluator-cdp",
    ) -> None:
        self._reads_spec = dict(reads_spec)
        self._assemble_fn = assemble_fn
        self._read_fn = read_fn
        self._via = via

    def acquire(
        self, task: Dict[str, Any], attempt_dir: Any
    ) -> Optional[Dict[str, Any]]:
        oracle_id = task["predicate"]["oracle"]
        specs = self._reads_spec.get(oracle_id)
        if specs is None:
            return None
        if self._read_fn is None:
            raise RuntimeError(
                "no evaluator read transport bound; "
                "trial-env CDP attach required for channel-backed oracles"
            )
        attempt_path = Path(attempt_dir)
        reads = self._read_fn(oracle_id, specs, task, attempt_path)
        return self._assemble_fn(
            oracle_id, task["task_id"], attempt_path.name, dict(reads), self._via
        )
