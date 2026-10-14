"""Contract tests for the TaskRunner seams (offline / fake-substrate only).

Covers: Protocol shapes, planner mapping tables, fake-substrate kernel
dispatch/refusal with exact event counts, SourcePort bundle schema,
tracking-bundle schema, and pinned-payload reproduction for the channel
driver. No browser, no planner inference, no authority gate required.
"""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import struct
import sys
import zlib
from pathlib import Path
from typing import Any, Dict

import pytest

from reflex.cognition.system2.planner import PlannedStep
from reflex.cognition.system2.providers import DeterministicRulePlanner
from reflex.evals.adapters.taskrunner_seams import (
    AuthorityNotGranted,
    BaselinePerceptionAdapter,
    EvalChannelDriver,
    FrameBoundSourcePort,
    HostKernelPort,
    PlannerAdapter,
    TrackingPerceptionAdapter,
    build_perception_arms,
    load_benchmark_channel_driver,
    map_planned_step,
)
from reflex.host.kernel.host_kernel import HostControlKernel
from reflex.perception.tracking.adapters import ModelRunAdapter
from reflex.perception.tracking.frame import FrameIdentity
from reflex.schemas.actions import ActionType, TypedAction
from reflex.schemas.delta import OutcomeClass, StateDelta
from reflex.schemas.policy import CapabilityPolicy
from reflex.schemas.state import (
    BoundingBox,
    CanonicalUIGraph,
    ModalitySource,
    NodeRole,
    UIStateNode,
)
from reflex.verification.settlement_observer import SettlementObserver

BENCH_ROOT = Path("/tmp/reflex-benchmarks-20261011")

# Structural P10 guard: adapter-added keys/values must never carry
# evaluator-only markers. (App content itself is passed through unmodified;
# the runner's audit judges content.)
FORBIDDEN_STRUCTURAL = (
    "evaluator",
    "oracle",
    "__EVAL__",
    "Runtime.evaluate",
    "hidden_state",
    "app_internal",
    "evaluator_channel",
)


def _png_bytes(width: int, height: int) -> bytes:
    def chunk(ctype: bytes, payload: bytes) -> bytes:
        out = struct.pack(">I", len(payload)) + ctype + payload
        return out + struct.pack(">I", zlib.crc32(ctype + payload) & 0xFFFFFFFF)

    raw = b"".join(b"\x00" + b"\x80\x80\x80" * width for _ in range(height))
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )


def _graph_dict() -> Dict[str, Any]:
    nodes = {
        "n1": UIStateNode(
            node_id="n1",
            role=NodeRole.BUTTON,
            bounds=BoundingBox(x1=10, y1=20, x2=110, y2=60),
            label="Submit",
            is_clickable=True,
            source=ModalitySource.DOM,
        ),
        "n2": UIStateNode(
            node_id="n2",
            role=NodeRole.INPUT,
            bounds=BoundingBox(x1=10, y1=80, x2=310, y2=110),
            label="Search",
            is_clickable=True,
            is_editable=True,
            source=ModalitySource.DOM,
        ),
    }
    graph = CanonicalUIGraph(
        timestamp_ms=1.0,
        nodes=nodes,
        url="http://127.0.0.1:9/",
        active_window_title="bench",
        viewport_size=(800, 600),
    )
    return graph.to_dict()


def _observation_bundle() -> Dict[str, Any]:
    pixels = _png_bytes(800, 600)
    digest = hashlib.sha256(pixels).hexdigest()
    frame = {
        "source_id": "cdp_chromium/linux",
        "frame_id": "f000001-test",
        "uid": "cdp_chromium/linux@f000001-test",
        "pixel_sha256": digest,
        "geometry": {"width_px": 800, "height_px": 600, "dpr": None},
    }
    return {
        "task_goal": "click button 'Submit'",
        "frame": frame,
        "frame_uid": frame["uid"],
        "pixel_sha256": digest,
        "geometry": dict(frame["geometry"]),
        "graph": _graph_dict(),
    }


def _static_parse_dict(
    frame_uid: str, *, source_id: str = "cdp_chromium/linux",
    frame_id: str = "f000001-test",
) -> Dict[str, Any]:
    frec = {
        "file": "frame_0001.png",
        "width": 800,
        "height": 600,
        "sha256": "ab" * 32,
        "condition": "test",
        "components": {
            "regions": {"backend": "fake-det"},
            "ocr": {"backend": "fake-ocr"},
            "caption": {"backend": "fake-cap"},
        },
        "regions": [
            {
                "region_id": 3,
                "box_xyxy": [10, 20, 110, 60],
                "score": 0.9,
                "merge_source": "det",
                "ocr_labels": "Submit",
            }
        ],
        "ocr": [
            {
                "ocr_id": 7,
                "box_xyxy": [12, 22, 100, 55],
                "polygon_xy": [[12, 22], [100, 22], [100, 55], [12, 55]],
                "text": "Submit",
                "confidence": 0.99,
            }
        ],
        "captions": [
            {
                "region_id": 3,
                "hypothesis_text": "submits the form",
                "uncertainty": {"mean_logprob": -0.2},
                "prompt": "p",
                "nearby_texts": [],
            }
        ],
        "failures": [],
    }
    parse = ModelRunAdapter(dpr=2.0).parse_frame_record(frec)
    assert parse.ok()
    data = parse.to_dict()
    # Rebind the test record to the observation frame under test.
    # (FrameIdentity uid is derived from source_id@frame_id on from_dict.)
    data["frame"]["source_id"] = source_id
    data["frame"]["frame_id"] = frame_id
    data["frame"]["uid"] = f"{source_id}@{frame_id}"
    assert data["frame"]["uid"] == frame_uid
    for coll in ("regions", "ocr", "hypotheses"):
        for entry in data[coll]:
            entry["frame_uid"] = frame_uid
    return data


def _assert_p10_clean(payload: Dict[str, Any]) -> None:
    blob = json.dumps(payload, sort_keys=True, default=str)
    for token in FORBIDDEN_STRUCTURAL:
        assert token not in blob, f"agent input leaks {token!r}"


# --------------------------------------------------------------------------
# PerceptionAdapter shapes (arms A/B/C/D)
# --------------------------------------------------------------------------

def test_perception_arm_a_shape() -> None:
    obs = _observation_bundle()
    out = BaselinePerceptionAdapter().agent_input(obs, [])
    assert BaselinePerceptionAdapter.arm == "A"
    assert out["arm"] == "A"
    assert out["frame_uid"] == obs["frame_uid"]
    assert out["pixel_sha256"] == obs["pixel_sha256"]
    assert out["geometry"] == {"width_px": 800, "height_px": 600, "dpr": None}
    assert CanonicalUIGraph.from_dict(out["graph"]).url == "http://127.0.0.1:9/"
    assert "tracking" not in out
    _assert_p10_clean(out)


def test_perception_arms_bcd_levels() -> None:
    obs = _observation_bundle()
    before = copy.deepcopy(obs)
    obs["static_parse"] = _static_parse_dict(obs["frame_uid"])
    arms = build_perception_arms()
    assert sorted(arms) == ["A", "B", "C", "D"]
    assert all(getattr(a, "arm", None) == k for k, a in arms.items())

    history = [{"input_digest": "abc123", "decision": {"kind": "act"}}]
    b = arms["B"].agent_input(obs, history)
    c = arms["C"].agent_input(obs, history)
    d = arms["D"].agent_input(obs, history)

    assert b["tracking"]["status"] == "ok"
    assert b["tracking"]["bound"] is True
    assert [r["region_id"] for r in b["tracking"]["regions"]] == ["r3"]
    assert "ocr" not in b["tracking"]
    assert "hypotheses" not in b["tracking"]

    assert [o["text"] for o in c["tracking"]["ocr"]] == ["Submit"]
    assert "hypotheses" not in c["tracking"]

    assert d["tracking"]["hypotheses"][0]["text"] == "submits the form"
    assert "confidence" not in d["tracking"]["hypotheses"][0]
    assert d["tracking"]["layout"]["num_regions"] == 1
    assert d["tracking"]["nodes"][0]["node_id"] == "vis:f000001-test:r3"
    assert d["history"] == [{"input_digest": "abc123", "kind": "act"}]

    for out in (b, c, d):
        _assert_p10_clean(out)
    # Tracking bundle consumed read-only: observation untouched.
    obs.pop("static_parse")
    assert obs == before


def test_perception_tracking_absent_and_unbound() -> None:
    obs = _observation_bundle()
    out = TrackingPerceptionAdapter("D").agent_input(obs, [])
    assert out["tracking"]["status"] == "not_run"

    obs["static_parse"] = _static_parse_dict(
        "other-source@other-frame", source_id="other-source",
        frame_id="other-frame",
    )
    out2 = TrackingPerceptionAdapter("B").agent_input(obs, [])
    assert out2["tracking"]["status"] == "ok"
    assert out2["tracking"]["bound"] is False

    with pytest.raises(ValueError):
        TrackingPerceptionAdapter("A")


# --------------------------------------------------------------------------
# PlannerAdapter mapping table
# --------------------------------------------------------------------------

def _planned(action: TypedAction, thought: str = "t") -> PlannedStep:
    return PlannedStep(
        thought_reasoning=thought,
        target_description="target",
        action=action,
        expected_delta=StateDelta(outcome_class=OutcomeClass.SUCCESS),
        confidence=0.9,
    )


def test_planner_fixed_decisions_map_to_act() -> None:
    adapter = PlannerAdapter(DeterministicRulePlanner())
    assert adapter.identity["planner"] == "DeterministicRulePlanner"
    obs = _observation_bundle()
    for goal in (
        "click button 'Submit'",
        "type 'hello' in Search",
        "navigate to http://127.0.0.1:9/",
        "do something unspecified",
    ):
        agent_input = BaselinePerceptionAdapter().agent_input(
            {**obs, "task_goal": goal}, []
        )
        decision = adapter.step(agent_input)
        assert decision["kind"] == "act", goal
        typed = TypedAction.from_dict(decision["action"])
        assert isinstance(typed.action_type, ActionType)
        if typed.coords is not None:
            assert 0.0 <= typed.coords.x <= 1.0
            assert 0.0 <= typed.coords.y <= 1.0


def test_planner_terminal_mapping_table() -> None:
    done = _planned(TypedAction(action_type=ActionType.NOOP,
                               metadata={"terminal": "done"}))
    assert map_planned_step(done) == {"kind": "done"}
    give_up = _planned(
        TypedAction(action_type=ActionType.WAIT, metadata={
            "terminal": "give_up", "give_up_reason": "no target"}),
        thought="stuck",
    )
    assert map_planned_step(give_up) == {"kind": "give_up", "reason": "no target"}
    fallback = _planned(
        TypedAction(action_type=ActionType.WAIT, metadata={"terminal": "give_up"}),
        thought="stuck with no reason",
    )
    assert map_planned_step(fallback)["reason"] == "stuck with no reason"
    act = map_planned_step(_planned(TypedAction(action_type=ActionType.CLICK)))
    assert act["kind"] == "act"
    TypedAction.from_dict(act["action"])

    class _DoneStub:
        async def plan_next_step(self, task_goal, current_state, history=None):  # noqa: ANN001,ANN202
            return done

    decision = PlannerAdapter(_DoneStub(), task_goal="g").step(
        {"task_goal": "", "graph": _graph_dict(), "history": []}
    )
    assert decision == {"kind": "done"}


# --------------------------------------------------------------------------
# KernelPort: fake-substrate dispatch / refusal with exact event counts
# --------------------------------------------------------------------------

def _click_action() -> Dict[str, Any]:
    return {
        "action_type": "click",
        "target_node_id": "n1",
        "target_label": "Submit",
        "coords": {"x": 0.075, "y": 0.0667},
        "text_payload": None,
        "key_code": None,
        "scroll_delta": None,
        "safety_class": "reversible",
        "metadata": {},
    }


def test_kernel_granted_receipt_and_exact_events() -> None:
    kernel = HostControlKernel(
        policy=CapabilityPolicy.permissive_policy(), settle_interval_s=0.0
    )
    port = HostKernelPort(kernel, session_id="seam-test")
    first = port.dispatch(_click_action())
    assert first["receipt"]["adapter_name"] == "kernel_mock_adapter"
    assert first["verification_passed"] is True
    assert len(port.events) == 1
    assert port.events[0]["event"] == "dispatched"
    port.dispatch(_click_action())
    port.dispatch(_click_action())
    assert len(port.events) == 3
    assert len({e["action_id"] for e in port.events}) == 3


def test_kernel_refused_zero_events() -> None:
    refused_policy = CapabilityPolicy(
        granted_scopes=set(),
        disallowed_domains=[],
        require_human_confirmation_for=set(),
        max_actions_per_session=500,
    )
    kernel = HostControlKernel(policy=refused_policy, settle_interval_s=0.0)
    port = HostKernelPort(kernel, session_id="seam-refused")
    with pytest.raises(AuthorityNotGranted):
        port.dispatch(_click_action())
    assert port.events == []
    with pytest.raises(AuthorityNotGranted):
        port.dispatch(_click_action())
    assert len(port.events) == 0


def test_kernel_injected_authority_error() -> None:
    class HarnessAuthority(Exception):
        pass

    refused_policy = CapabilityPolicy(
        granted_scopes=set(),
        disallowed_domains=[],
        require_human_confirmation_for=set(),
        max_actions_per_session=500,
    )
    kernel = HostControlKernel(policy=refused_policy, settle_interval_s=0.0)
    port = HostKernelPort(
        kernel, session_id="seam-injected", authority_error=HarnessAuthority
    )
    with pytest.raises(HarnessAuthority):
        port.dispatch(_click_action())
    assert port.events == []


def _load_harness_module(name: str, relpath: str):  # type: ignore[no-untyped-def]
    import types

    path = BENCH_ROOT / relpath
    if not path.is_file():
        pytest.skip(f"benchmark harness not present: {path}")
    pkg_name = "seam_harness_pkg"
    if pkg_name not in sys.modules:
        pkg = types.ModuleType(pkg_name)
        pkg.__path__ = [str(BENCH_ROOT / "harness")]
        sys.modules[pkg_name] = pkg
    full = f"{pkg_name}.{name}"
    if full in sys.modules:
        return sys.modules[full]
    spec = importlib.util.spec_from_file_location(full, str(path))
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[full] = module
    spec.loader.exec_module(module)
    return module


def test_kernel_refusal_maps_to_harness_cancelled(tmp_path: Path) -> None:
    taskrunner = _load_harness_module("seam_taskrunner", "harness/taskrunner.py")

    class _Ledger:
        """Minimal fake ledger."""

        def __init__(self) -> None:
            self.calls: list = []

        def plan(self, *a: Any, **k: Any) -> None:
            self.calls.append("plan")

        def start(self, *a: Any, **k: Any) -> None:
            self.calls.append("start")

        def observe(self, *a: Any, **k: Any) -> None:
            self.calls.append("observe")

        def action(self, *a: Any, **k: Any) -> None:
            self.calls.append("action")

        def cost(self, *a: Any, **k: Any) -> None:
            self.calls.append("cost")

        def terminal(self, *a: Any, **k: Any) -> None:
            self.calls.append(("terminal", a[1] if len(a) > 1 else k))

    class _Evaluator:
        def score(self, task: Any, datadir: Any, payload: Any) -> Any:  # noqa: ANN001,ANN401
            raise AssertionError("cancelled attempts must not be scored")

    class _Apps:
        def start(self, family: str, attempt_dir: Path) -> Dict[str, Any]:
            return {"family": family}

        def stop(self, handle: Dict[str, Any]) -> Dict[str, Any]:
            return {"stopped": True}

    class _Channel:
        def acquire(self, task: Any, attempt_dir: Path) -> Any:  # noqa: ANN001,ANN401
            raise AssertionError("cancelled attempts must not acquire")

    class _Source:
        def observe(self) -> Dict[str, Any]:
            return _observation_bundle()

    class _Planner:
        identity = {"planner": "stub"}

        def step(self, agent_input: Dict[str, Any]) -> Dict[str, Any]:
            return {"kind": "act", "action": _click_action()}

    refused_policy = CapabilityPolicy(
        granted_scopes=set(),
        disallowed_domains=[],
        require_human_confirmation_for=set(),
        max_actions_per_session=500,
    )
    kernel = HostControlKernel(policy=refused_policy, settle_interval_s=0.0)
    port = HostKernelPort(
        kernel, session_id="seam-harness", authority_error=taskrunner.AuthorityNotGranted
    )
    runner = taskrunner.TaskRunner(
        ledger=_Ledger(),
        evaluator=_Evaluator(),
        planner=_Planner(),
        kernel=port,
        source=_Source(),
        perception={"A": BaselinePerceptionAdapter()},
        channel=_Channel(),
        apps=_Apps(),
        run_root=tmp_path,
    )
    task = {
        "task_id": "SEAM-01",
        "app_family": "todomvc",
        "attempt_plan": {
            "arms": ["A"],
            "repetitions": 1,
            "limits": {"max_physical_actions": 2, "max_model_calls": 2,
                       "max_minutes": 5},
        },
    }
    cfg = taskrunner.AttemptConfig(
        task=task, arm="A", repetition=0, attempt_id="SEAM-01-A-r0"
    )
    result = runner.run_attempt(cfg, {})
    assert result["status"] == "CANCELLED"
    assert result["detail"]["reason"] == "authority-refused"
    assert port.events == []


# --------------------------------------------------------------------------
# SourcePort bundle schema
# --------------------------------------------------------------------------

class _FakeProvider:
    session_epoch = "epoch-test"

    def __init__(self, pixels: bytes) -> None:
        self._pixels = pixels

    async def capture_state(self) -> Dict[str, Any]:
        return _graph_dict()

    async def capture_screenshot(self) -> bytes:
        return self._pixels


def test_source_bundle_schema() -> None:
    pixels = _png_bytes(800, 600)
    port = FrameBoundSourcePort(_FakeProvider(pixels), settlement=SettlementObserver())
    bundle = port.observe()
    assert bundle["pixel_sha256"] == hashlib.sha256(pixels).hexdigest()
    assert bundle["frame_uid"].startswith("cdp_chromium/linux@")
    assert bundle["frame"]["uid"] == bundle["frame_uid"]
    assert bundle["frame"]["pixel_sha256"] == bundle["pixel_sha256"]
    assert bundle["geometry"]["width_px"] == 800
    assert bundle["geometry"]["height_px"] == 600
    assert bundle["geometry"]["dpr"] is None
    assert bundle["screenshot_len"] == len(pixels)
    assert bundle["settlement"]["settled"] is True
    assert bundle["settlement"]["in_flight"] == 0
    assert bundle["graph"]["url"] == "http://127.0.0.1:9/"
    assert FrameIdentity.from_dict(bundle["frame"]).uid == bundle["frame_uid"]
    assert any(u["feature"] == "dpr" for u in bundle["unsupported"])
    json.dumps(bundle, default=str)


def test_source_frame_binding_unique_no_observer() -> None:
    pixels = _png_bytes(64, 32)
    port = FrameBoundSourcePort(_FakeProvider(pixels))
    first = port.observe()
    second = port.observe()
    assert first["frame_uid"] != second["frame_uid"]
    assert first["pixel_sha256"] == second["pixel_sha256"]
    assert first["geometry"]["width_px"] == 64
    assert first["geometry"]["height_px"] == 32
    assert first["settlement"]["settled"] is None

    with pytest.raises(ValueError):
        FrameBoundSourcePort(provider=None, session=object())


# --------------------------------------------------------------------------
# ChannelDriver: pinned-payload reproduction
# --------------------------------------------------------------------------

def test_channel_acquire_reproduces_pinned_bytes(tmp_path: Path) -> None:
    reads_spec, assemble = load_benchmark_channel_driver(BENCH_ROOT / "scripts")
    assert "todomvc_ls" in reads_spec
    fixture = {
        "todos": {"todos": [{"title": "Buy oat milk DEV-T01", "completed": False}]},
        "rendered": 1,
    }
    driver = EvalChannelDriver(
        reads_spec=reads_spec, assemble_fn=assemble,
        read_fn=lambda oracle, specs, task, attempt_dir: dict(fixture),
    )
    task = {"task_id": "DEV-T01", "predicate": {"oracle": "todomvc_ls"}}
    attempt_dir = tmp_path / "DEV-T01-A-r0"
    attempt_dir.mkdir()
    payload = driver.acquire(task, attempt_dir)
    assert payload is not None
    expected = assemble("todomvc_ls", "DEV-T01", "DEV-T01-A-r0", dict(fixture))
    for key in ("oracle", "task_id", "attempt_id", "via", "state", "channel", "reads"):
        assert payload[key] == expected[key], key
    assert payload["attempt_id"] == "DEV-T01-A-r0"


def test_channel_disk_backed_none_and_no_transport() -> None:
    reads_spec, assemble = load_benchmark_channel_driver(
        BENCH_ROOT / "scripts" / "channel_driver.py"
    )
    offline = EvalChannelDriver(reads_spec=reads_spec, assemble_fn=assemble)
    assert offline.acquire(
        {"task_id": "T", "predicate": {"oracle": "tiddlywiki_files"}}, Path("/tmp/x")
    ) is None
    with pytest.raises(RuntimeError, match="no evaluator read transport"):
        offline.acquire(
            {"task_id": "T", "predicate": {"oracle": "todomvc_ls"}}, Path("/tmp/x")
        )
