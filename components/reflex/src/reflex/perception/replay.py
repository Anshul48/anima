"""Recorded-frame replay source on the public ObservationPort contract.

A recording is a directory of frame bundles: one observation JSON plus its PNG
pixels per frame, with a manifest carrying digests and source identity.
ReplaySource serves those frames through the same capture_observation /
compute_delta interface as a live source, so library, service, and replay
runners exercise one contract.

Replay provenance is explicit: served observations keep their recorded IDs
(so IDs resolve to recorded bytes), carry replay=true metadata, and carry
clock_domain=replay plus live_action_eligible=false flags through every
public API. Recorded timestamps are preserved (usually stale against a live
clock), but a just-recorded frame may still fall inside a freshness window,
so freshness alone never qualifies replayed frames for live action.
Tampered observation JSON, graph evidence, or pixels fail closed as corrupt;
missing frames fail as unavailable; both are explicit, never silent.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from reflex.ports.clock import ClockPort, SystemClock
from reflex.ports.observation import ObservationPort
from reflex.schemas.observation import (
    CorruptedObservationError,
    ObservationQuality,
    ObservationRecord,
    PerceptionError,
)
from reflex.schemas.state import CanonicalUIGraph


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class RecordedFrame:
    """One recorded frame bundle: observation JSON plus optional PNG pixels."""

    frame_id: str
    observation: ObservationRecord
    png_bytes: Optional[bytes]
    png_sha256: Optional[str]
    recorded_wall_utc: str


class RecordingWriter:
    """Appends observation + pixel bundles to a recording directory."""

    def __init__(
        self,
        recording_dir: Union[str, Path],
        source_identity: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.recording_dir = Path(recording_dir)
        self.frames_dir = self.recording_dir / "frames"
        self.frames_dir.mkdir(parents=True, exist_ok=True)
        self.source_identity = dict(source_identity or {})
        self.frame_ids: List[str] = []
        existing = self.recording_dir / "manifest.json"
        if existing.exists():
            manifest = json.loads(existing.read_text(encoding="utf-8"))
            self.frame_ids = [f["frame_id"] for f in manifest.get("frames", [])]

    def write(self, observation: ObservationRecord) -> RecordedFrame:
        png = observation.screenshot_bytes
        digest = sha256_bytes(png) if png is not None else None
        frame = RecordedFrame(
            frame_id=observation.observation_id,
            observation=observation,
            png_bytes=png,
            png_sha256=digest,
            recorded_wall_utc=datetime.now(timezone.utc).isoformat(),
        )
        (self.frames_dir / f"{frame.frame_id}.json").write_text(
            json.dumps(observation.to_dict(include_screenshot_bytes=True), indent=1) + "\n",
            encoding="utf-8",
        )
        if png is not None:
            (self.frames_dir / f"{frame.frame_id}.png").write_bytes(png)
        if frame.frame_id not in self.frame_ids:
            self.frame_ids.append(frame.frame_id)
        self._write_manifest()
        return frame

    def _write_manifest(self) -> None:
        frames = []
        for frame_id in self.frame_ids:
            json_path = self.frames_dir / f"{frame_id}.json"
            raw_json = json_path.read_bytes()
            payload = json.loads(raw_json.decode("utf-8"))
            png_path = self.frames_dir / f"{frame_id}.png"
            graph = ObservationRecord.from_dict(
                payload,
                screenshot_bytes=png_path.read_bytes() if png_path.exists() else None,
            ).graph
            frames.append(
                {
                    "frame_id": frame_id,
                    "observation_id": payload.get("observation_id"),
                    "timestamp_ms": payload.get("timestamp_ms"),
                    "quality": payload.get("quality"),
                    "observation_sha256": sha256_bytes(raw_json),
                    "graph_evidence_sha256": graph.compute_evidence_hash(),
                    "png_sha256": sha256_bytes(png_path.read_bytes()) if png_path.exists() else None,
                }
            )
        manifest = {
            "recording_id": self.recording_dir.name,
            "source_identity": self.source_identity,
            "frames": frames,
        }
        (self.recording_dir / "manifest.json").write_text(
            json.dumps(manifest, indent=1) + "\n", encoding="utf-8"
        )

    def manifest(self) -> Dict[str, Any]:
        return json.loads((self.recording_dir / "manifest.json").read_text(encoding="utf-8"))


class ReplaySource(ObservationPort):
    """ObservationPort serving recorded frames in order, with explicit seek.

    capture_observation() serves the current frame and advances the cursor, so
    consecutive captures walk the recording. capture_state() and
    capture_screenshot() serve the current frame without advancing, keeping
    tree and pixels coherent. seek(frame_id) repositions; unknown IDs raise
    PerceptionError. Pixel digests are verified on every serve: tampering
    raises CorruptedObservationError and a missing PNG raises PerceptionError.
    """

    def __init__(
        self,
        recording_dir: Union[str, Path],
        clock: Optional[ClockPort] = None,
    ) -> None:
        self.recording_dir = Path(recording_dir)
        self.frames_dir = self.recording_dir / "frames"
        self.clock = clock or SystemClock()
        manifest_path = self.recording_dir / "manifest.json"
        if not manifest_path.exists():
            raise PerceptionError(f"Recording has no manifest: {self.recording_dir}")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.recording_id: str = manifest.get("recording_id", self.recording_dir.name)
        self.source_identity: Dict[str, Any] = manifest.get("source_identity", {})
        self.frame_ids: List[str] = [f["frame_id"] for f in manifest.get("frames", [])]
        if not self.frame_ids:
            raise PerceptionError(f"Recording has no frames: {self.recording_dir}")
        self.expected_digests: Dict[str, Optional[str]] = {
            f["frame_id"]: f.get("png_sha256") for f in manifest.get("frames", [])
        }
        self.expected_json_digests: Dict[str, Optional[str]] = {
            f["frame_id"]: f.get("observation_sha256") for f in manifest.get("frames", [])
        }
        self.expected_graph_digests: Dict[str, Optional[str]] = {
            f["frame_id"]: f.get("graph_evidence_sha256") for f in manifest.get("frames", [])
        }
        self._cursor = 0

    @property
    def cursor_frame_id(self) -> str:
        return self.frame_ids[min(self._cursor, len(self.frame_ids) - 1)]

    def seek(self, frame_id: str) -> None:
        if frame_id not in self.frame_ids:
            raise PerceptionError(
                f"Unknown replay frame '{frame_id}' in recording '{self.recording_id}'."
            )
        self._cursor = self.frame_ids.index(frame_id)

    def _load_frame(self, frame_id: str) -> RecordedFrame:
        json_path = self.frames_dir / f"{frame_id}.json"
        if not json_path.exists():
            raise PerceptionError(
                f"Replay frame '{frame_id}' is missing from recording '{self.recording_id}'."
            )
        raw_json = json_path.read_bytes()
        expected_json = self.expected_json_digests.get(frame_id)
        if expected_json is not None and sha256_bytes(raw_json) != expected_json:
            raise CorruptedObservationError(
                f"Replay frame '{frame_id}' observation JSON does not match manifest digest; "
                "recording was tampered with."
            )
        payload = json.loads(raw_json.decode("utf-8"))
        png_path = self.frames_dir / f"{frame_id}.png"
        png: Optional[bytes] = png_path.read_bytes() if png_path.exists() else None
        expected = self.expected_digests.get(frame_id)
        if png is not None and expected is not None and sha256_bytes(png) != expected:
            raise CorruptedObservationError(
                f"Replay frame '{frame_id}' pixels do not match manifest digest; "
                "recording was tampered with."
            )
        if png is None and expected is not None:
            raise PerceptionError(
                f"Replay frame '{frame_id}' references PNG digest {expected[:12]}... "
                "but the pixel file is missing."
            )
        observation = ObservationRecord.from_dict(payload, screenshot_bytes=png)
        expected_graph = self.expected_graph_digests.get(frame_id)
        if expected_graph is not None and observation.graph.compute_evidence_hash() != expected_graph:
            raise CorruptedObservationError(
                f"Replay frame '{frame_id}' graph evidence does not match manifest digest; "
                "recording was tampered with."
            )
        return RecordedFrame(
            frame_id=frame_id,
            observation=observation,
            png_bytes=png,
            png_sha256=expected,
            recorded_wall_utc="",
        )

    def _serve_current(self) -> ObservationRecord:
        frame = self._load_frame(self.cursor_frame_id)
        metadata = dict(frame.observation.platform_metadata)
        metadata.update(
            {
                "replay": True,
                "recording_id": self.recording_id,
                "replay_frame_id": frame.frame_id,
                "replay_png_sha256": frame.png_sha256,
                # Explicit replay clock domain: a just-recorded frame may
                # still fall inside a freshness window, so freshness alone
                # never qualifies replayed frames for live action. These
                # flags travel through to_dict/from_dict and the service.
                "clock_domain": "replay",
                "live_action_eligible": False,
            }
        )
        return replace(
            frame.observation,
            source_adapter="replay_source",
            platform_metadata=metadata,
        )

    async def capture_state(self) -> CanonicalUIGraph:
        return self._serve_current().graph

    async def capture_screenshot(self) -> bytes:
        frame = self._load_frame(self.cursor_frame_id)
        if frame.png_bytes is None:
            raise PerceptionError(
                f"Replay frame '{frame.frame_id}' has no recorded pixels."
            )
        return frame.png_bytes

    async def capture_observation(self) -> ObservationRecord:
        obs = self._serve_current()
        if self._cursor < len(self.frame_ids) - 1:
            self._cursor += 1
        return obs
