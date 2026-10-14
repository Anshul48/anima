"""Local perception service client (stdlib urllib)."""

from __future__ import annotations

import base64
import hashlib
import json
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

from reflex.schemas.observation import (
    CorruptedObservationError,
    ObservationRecord,
    PerceptionDelta,
    validate_screenshot_bytes,
)


class ServiceError(Exception):
    def __init__(self, status: int, payload: Dict[str, Any]) -> None:
        super().__init__(f"service HTTP {status}: {payload}")
        self.status = status
        self.payload = payload


class PerceptionServiceClient:
    def __init__(self, base_url: str, timeout_s: float = 30.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s

    def _request(self, method: str, route: str, body: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        data = json.dumps(body or {}).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}/{route.lstrip('/')}",
            data=data if method == "POST" else None,
            headers={"Content-Type": "application/json"},
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_s) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            try:
                payload = json.loads(exc.read().decode("utf-8"))
            except Exception:
                payload = {"error": "unreadable-error-body"}
            raise ServiceError(exc.code, payload) from exc

    def health(self) -> Dict[str, Any]:
        return self._request("GET", "healthz")

    @staticmethod
    def decode_observation(payload: Dict[str, Any]) -> ObservationRecord:
        """Decodes a served observation after verifying its pixel evidence.

        The PNG digest, decodability, decoded dimensions (against the served
        modality claim), and frame ID are all verified BEFORE a healthy
        observation object is returned. Client-side failures raise
        ServiceError with status 0.
        """
        b64 = payload.get("screenshot_b64")
        png = base64.b64decode(b64) if b64 is not None else None
        expected_sha = payload.get("png_sha256")
        if png is not None:
            actual_sha = hashlib.sha256(png).hexdigest()
            if expected_sha is not None and actual_sha != expected_sha:
                raise ServiceError(0, {
                    "error": "pixel-digest-mismatch",
                    "expected_sha256": expected_sha,
                    "actual_sha256": actual_sha,
                })
            try:
                width, height = validate_screenshot_bytes(png)
            except CorruptedObservationError as exc:
                raise ServiceError(0, {
                    "error": "pixel-undecodable", "message": str(exc)[:300],
                }) from exc
            modality = (
                payload.get("observation", {}).get("platform_metadata", {})
                .get("modality_status", {}).get("screenshot", "")
            )
            if isinstance(modality, str) and modality.startswith("ok: "):
                claimed = modality[len("ok: "):]
                if claimed != f"{width}x{height}":
                    raise ServiceError(0, {
                        "error": "pixel-dimension-mismatch",
                        "claimed": claimed,
                        "decoded": f"{width}x{height}",
                    })
        obs_dict = payload.get("observation", {})
        if not obs_dict.get("observation_id"):
            raise ServiceError(0, {"error": "missing-frame-id"})
        return ObservationRecord.from_dict(obs_dict, screenshot_bytes=png)

    def observe(self) -> ObservationRecord:
        return self.decode_observation(self._request("POST", "observe"))

    def update(self, previous_observation_id: str):
        payload = self._request("POST", "update", {"previous_observation_id": previous_observation_id})
        return self.decode_observation(payload), PerceptionDelta.from_dict(payload["delta"])

    def query(self, observation_id: str, by: str, value: str) -> List[Dict[str, Any]]:
        payload = self._request(
            "POST", "query",
            {"observation_id": observation_id, "selector": {"by": by, "value": value}},
        )
        return payload["nodes"]

    def shutdown(self) -> Dict[str, Any]:
        return self._request("POST", "shutdown")
