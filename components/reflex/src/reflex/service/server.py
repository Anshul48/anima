"""Local perception service server (stdlib http.server, localhost only)."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, Optional, OrderedDict as OrderedDictType
from collections import OrderedDict

from reflex.ports.observation import ObservationPort
from reflex.schemas.observation import ObservationRecord


def _png_digest(png: Optional[bytes]) -> Optional[str]:
    return hashlib.sha256(png).hexdigest() if png is not None else None


def _serialize_observation(obs: ObservationRecord) -> Dict[str, Any]:
    png = obs.screenshot_bytes
    return {
        "observation": obs.to_dict(include_screenshot_bytes=True),
        "screenshot_b64": base64.b64encode(png).decode("ascii") if png is not None else None,
        "png_sha256": _png_digest(png),
    }


class PerceptionServiceServer:
    """Binds one ObservationPort and serves it over localhost HTTP."""

    def __init__(
        self,
        source: Optional[ObservationPort],
        host: str = "127.0.0.1",
        port: int = 0,
        retention: int = 64,
        on_shutdown: Optional[Any] = None,
    ) -> None:
        self.source = source
        self.host = host
        self.port = port
        self.retention = retention
        self._on_shutdown = on_shutdown
        self._snapshots: OrderedDictType[str, ObservationRecord] = OrderedDict()
        self._lock = threading.Lock()
        self._httpd: Optional[ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._loop_thread: Optional[threading.Thread] = None

    @property
    def base_url(self) -> str:
        assert self._httpd is not None
        host, port = self._httpd.server_address
        return f"http://{host}:{port}"

    def _retain(self, obs: ObservationRecord) -> None:
        with self._lock:
            self._snapshots[obs.observation_id] = obs
            while len(self._snapshots) > self.retention:
                self._snapshots.popitem(last=False)

    def _lookup(self, observation_id: str) -> Optional[ObservationRecord]:
        with self._lock:
            return self._snapshots.get(observation_id)

    @property
    def loop(self) -> asyncio.AbstractEventLoop:
        assert self._loop is not None, "server loop not started"
        return self._loop

    def run(self, coro, timeout: float = 60.0):
        """Runs a source coroutine on the server's dedicated event loop.

        All source coroutines share one loop, so persistent transports
        (e.g. live CDP websockets) stay bound to the loop that created them.
        """
        future = asyncio.run_coroutine_threadsafe(coro, self.loop)
        return future.result(timeout=timeout)

    def _run_coro(self, coro):
        return self.run(coro)

    def _handle(self, route: str, body: Dict[str, Any]):
        if route == "healthz":
            if self.source is None:
                return 200, {"status": "starting", "source_adapter": None}
            epoch = getattr(self.source, "session_epoch", None)
            recording = getattr(self.source, "recording_id", None)
            return 200, {
                "status": "ok",
                "source_adapter": type(self.source).__name__,
                "session_epoch": epoch,
                "recording_id": recording,
                "retained_snapshots": len(self._snapshots),
            }
        if self.source is None and route in ("observe", "update", "query"):
            return 503, {"error": "source-unbound", "detail": "Service source not attached yet."}
        if route == "observe":
            assert self.source is not None
            obs = self._run_coro(self.source.capture_observation())
            self._retain(obs)
            return 200, _serialize_observation(obs)
        if route == "update":
            prev_id = body.get("previous_observation_id")
            prev = self._lookup(str(prev_id)) if prev_id else None
            if prev is None:
                return 404, {
                    "error": "unavailable-reference",
                    "previous_observation_id": prev_id,
                    "detail": "No retained snapshot with that ID; request a fresh observe.",
                }
            assert self.source is not None
            curr = self._run_coro(self.source.capture_observation())
            self._retain(curr)
            delta = self.source.compute_delta(prev, curr)
            payload = _serialize_observation(curr)
            payload["delta"] = delta.to_dict()
            return 200, payload
        if route == "query":
            obs_id = body.get("observation_id")
            snapshot = self._lookup(str(obs_id)) if obs_id else None
            if snapshot is None:
                return 404, {
                    "error": "unavailable-reference",
                    "observation_id": obs_id,
                }
            selector = body.get("selector", {}) or {}
            mode = selector.get("by", "id")
            value = selector.get("value", "")
            nodes = snapshot.graph.nodes
            if mode == "id":
                matched = [nodes[str(value)].to_dict()] if str(value) in nodes else []
            elif mode == "role":
                matched = [n.to_dict() for n in nodes.values() if n.role.value == value]
            elif mode == "label":
                matched = [n.to_dict() for n in nodes.values() if value in (n.label or "")]
            else:
                return 400, {"error": "bad-selector", "selector": selector}
            return 200, {"observation_id": snapshot.observation_id, "nodes": matched}
        if route == "shutdown":
            threading.Thread(target=self.stop, daemon=True).start()
            return 200, {"status": "shutting-down"}
        return 404, {"error": "unknown-route", "route": route}

    def start(self) -> "PerceptionServiceServer":
        server = self

        class Handler(BaseHTTPRequestHandler):
            server_version = "ReflexPerception/1"

            def log_message(self, *args):  # quiet
                pass

            def _send(self, status: int, payload: Dict[str, Any]) -> None:
                data = json.dumps(payload).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self) -> None:
                if self.path.rstrip("/") in ("", "/healthz"):
                    status, payload = server._handle("healthz", {})
                else:
                    status, payload = 404, {"error": "unknown-route", "route": self.path}
                self._send(status, payload)

            def do_POST(self) -> None:
                length = int(self.headers.get("Content-Length", "0") or "0")
                raw = self.rfile.read(length) if length else b"{}"
                try:
                    body = json.loads(raw.decode("utf-8") or "{}")
                except json.JSONDecodeError:
                    self._send(400, {"error": "bad-json"})
                    return
                route = self.path.strip("/")
                try:
                    status, payload = server._handle(route, body if isinstance(body, dict) else {})
                except Exception as exc:
                    status, payload = 500, {
                        "error": "source-failure",
                        "exception": type(exc).__name__,
                        "message": str(exc)[:500],
                    }
                self._send(status, payload)

        self._loop = asyncio.new_event_loop()
        self._loop_thread = threading.Thread(target=self._loop.run_forever, daemon=True)
        self._loop_thread.start()
        self._httpd = ThreadingHTTPServer((self.host, self.port), Handler)
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        if self._on_shutdown is not None:
            callback, self._on_shutdown = self._on_shutdown, None
            try:
                callback()
            except Exception:
                pass
        with self._lock:
            httpd, thread = self._httpd, self._thread
            loop, loop_thread = self._loop, self._loop_thread
            self._httpd = None
            self._thread = None
            self._loop = None
            self._loop_thread = None
        if httpd is not None:
            try:
                httpd.shutdown()
            except Exception:
                pass
            try:
                httpd.server_close()
            except Exception:
                pass
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=5.0)
        if loop is not None:
            try:
                loop.call_soon_threadsafe(loop.stop)
            except Exception:
                pass
        if loop_thread is not None and loop_thread is not threading.current_thread():
            loop_thread.join(timeout=5.0)
        if loop is not None:
            try:
                loop.close()
            except Exception:
                pass


def serve_forever(source: ObservationPort, host: str = "127.0.0.1", port: int = 0) -> None:
    """Runs the service in the foreground; prints the base URL for runners."""
    server = PerceptionServiceServer(source, host=host, port=port).start()
    print(f"REFLEX_SERVICE_URL={server.base_url}", flush=True)
    try:
        assert server._thread is not None
        server._thread.join()
    except KeyboardInterrupt:
        server.stop()
