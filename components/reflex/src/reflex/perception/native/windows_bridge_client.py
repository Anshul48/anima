"""Reflex Windows Host Bridge Client for WSL2 / Remote Execution.

Provides HTTP/REST client connecting WSL2 Linux Reflex instances to a native
Windows host bridge daemon running on localhost or a configured bridge endpoint.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from typing import Any, Dict, List, Optional
import urllib.error
import urllib.request

from reflex.schemas.state import BoundingBox, CanonicalUIGraph, ModalitySource, NodeRole, UIStateNode


@dataclass(frozen=True)
class WindowsBridgeConfig:
    """Configuration for connecting to native Windows host bridge daemon."""
    bridge_url: str = "http://127.0.0.1:49152"
    timeout_s: float = 2.0

    @classmethod
    def from_env(cls) -> WindowsBridgeConfig:
        url = os.environ.get("REFLEX_WINDOWS_BRIDGE_URL", "http://127.0.0.1:49152")
        return cls(bridge_url=url.rstrip("/"))


class WindowsBridgeClient:
    """HTTP client communicating with native Windows UI Automation bridge daemon."""

    def __init__(self, config: Optional[WindowsBridgeConfig] = None) -> None:
        self.config = config or WindowsBridgeConfig.from_env()
        self.base_url = self.config.bridge_url.rstrip("/")
        self.timeout_s = self.config.timeout_s
        self._is_connected = False

    @property
    def is_connected(self) -> bool:
        return self._is_connected

    def _http_get(self, endpoint: str) -> Any:
        """Synchronous HTTP GET request using standard library urllib."""
        url = f"{self.base_url}{endpoint}"
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Reflex-WSL2-BridgeClient/1.0", "Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
            data = resp.read()
            content_type = resp.headers.get("Content-Type", "")
            if "application/json" in content_type:
                return json.loads(data.decode("utf-8"))
            return data

    async def check_health(self) -> Dict[str, Any]:
        """Checks if the native Windows bridge daemon is running and reachable."""
        try:
            resp = self._http_get("/health")
            if isinstance(resp, dict) and resp.get("status") == "ok":
                self._is_connected = True
                return resp
        except Exception:
            self._is_connected = False
        return {"status": "unreachable", "is_live": False}

    async def list_open_windows(self) -> List[str]:
        """Queries the bridge for open top-level Windows application windows."""
        try:
            resp = self._http_get("/windows")
            if isinstance(resp, dict) and "windows" in resp:
                return [str(w) for w in resp["windows"]]
            elif isinstance(resp, list):
                return [str(w) for w in resp]
        except Exception:
            pass
        return []

    async def get_active_window_title(self) -> Optional[str]:
        """Queries the title of the currently focused window on the Windows host."""
        try:
            resp = self._http_get("/active_window/title")
            if isinstance(resp, dict):
                return resp.get("title")
        except Exception:
            pass
        return None

    def capture_active_window_sync(self, max_depth: int = 50) -> Optional[CanonicalUIGraph]:
        """Synchronously fetches the active window accessibility tree across the bridge."""
        try:
            resp = self._http_get(f"/active_window/tree?max_depth={max_depth}")
            if isinstance(resp, dict) and "nodes" in resp:
                timestamp_ms = float(resp.get("timestamp_ms", 0.0))
                window_title = resp.get("active_window_title")
                nodes: Dict[str, UIStateNode] = {}
                for node_id, n_data in resp.get("nodes", {}).items():
                    bounds_data = n_data.get("bounds", [0, 0, 100, 30])
                    if isinstance(bounds_data, (list, tuple)) and len(bounds_data) == 4:
                        bounds = BoundingBox(bounds_data[0], bounds_data[1], bounds_data[2], bounds_data[3])
                    elif isinstance(bounds_data, dict):
                        bounds = BoundingBox.from_dict(bounds_data)
                    else:
                        bounds = BoundingBox(0, 0, 100, 30)

                    role_val = n_data.get("role", "unknown")
                    try:
                        role = NodeRole(role_val)
                    except Exception:
                        role = NodeRole.UNKNOWN

                    nodes[node_id] = UIStateNode(
                        node_id=node_id,
                        role=role,
                        bounds=bounds,
                        label=n_data.get("label", ""),
                        value=n_data.get("value", ""),
                        is_clickable=bool(n_data.get("is_clickable", True)),
                        is_editable=bool(n_data.get("is_editable", False)),
                        is_focused=bool(n_data.get("is_focused", False)),
                        is_enabled=bool(n_data.get("is_enabled", True)),
                        parent_id=n_data.get("parent_id"),
                        children_ids=list(n_data.get("children_ids", [])),
                        source=ModalitySource.UIA,
                        confidence=1.0,
                        attributes=dict(n_data.get("attributes", {})),
                    )

                return CanonicalUIGraph(
                    timestamp_ms=timestamp_ms,
                    nodes=nodes,
                    focused_node_id=resp.get("focused_node_id"),
                    active_window_title=window_title,
                    viewport_size=(
                        int(resp.get("viewport_size", [1920, 1080])[0]),
                        int(resp.get("viewport_size", [1920, 1080])[1]),
                    ),
                )
        except Exception:
            pass
        return None

    def capture_screenshot_sync(self) -> Optional[bytes]:
        """Synchronously fetches active desktop screenshot bytes across the bridge."""
        try:
            resp = self._http_get("/active_window/screenshot")
            if isinstance(resp, bytes) and len(resp) > 0:
                return resp
        except Exception:
            pass
        return None

    async def capture_active_window(self, max_depth: int = 50) -> Optional[CanonicalUIGraph]:
        """Fetches the active window accessibility tree across the bridge."""
        return self.capture_active_window_sync(max_depth=max_depth)

    async def capture_screenshot(self) -> Optional[bytes]:
        """Fetches active desktop screenshot bytes across the bridge."""
        return self.capture_screenshot_sync()

    async def close(self) -> None:
        """Closes bridge client session."""
        self._is_connected = False
