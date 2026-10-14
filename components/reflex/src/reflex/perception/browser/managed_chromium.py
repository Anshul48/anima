"""Managed Chromium Observation & Direct CDP Driver for Reflex.

Provides deterministic Chromium discovery, child process lifecycle management,
a robust CDP WebSocket client with request-response correlation and event subscriptions,
and a high-level ManagedChromiumSession async context manager.
"""

from __future__ import annotations

import asyncio
import base64
from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
from typing import Any, Awaitable, Callable, Dict, List, Optional, Sequence, Set, Tuple, Union
import urllib.error
import urllib.request
import websockets

from reflex.perception.browser.cdp_provider import (
    CDPObservationProvider,
    CDPSessionProtocol,
)
from reflex.execution.browser.cdp_action_adapter import CDPActionAdapter
from reflex.schemas.state import CanonicalUIGraph


class CDPError(Exception):
    """Exception raised when a Chrome DevTools Protocol command fails."""

    def __init__(
        self,
        message: str,
        code: Optional[int] = None,
        data: Optional[Any] = None,
    ) -> None:
        prefix = f"CDP Error {code}: " if code is not None else "CDP Error: "
        super().__init__(f"{prefix}{message}")
        self.message = message
        self.code = code
        self.data = data


class CDPConnectionClosedError(CDPError):
    """Exception raised when CDP WebSocket connection is closed unexpectedly."""

    def __init__(self, message: str = "CDP WebSocket connection was closed") -> None:
        super().__init__(message=message, code=-32000)


class ChromiumDiscovery:
    """Discovers installed Chromium, Google Chrome, and Microsoft Edge executables."""

    ENV_VARS: List[str] = [
        "CHROMIUM_PATH",
        "CHROME_PATH",
        "EDGE_PATH",
        "CHROME_BIN",
        "BROWSER_PATH",
    ]

    WINDOWS_PATHS: List[str] = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe",
        r"%LOCALAPPDATA%\Microsoft\Edge\Application\msedge.exe",
        r"%PROGRAMFILES%\Google\Chrome\Application\chrome.exe",
        r"%PROGRAMFILES(X86)%\Google\Chrome\Application\chrome.exe",
        r"%PROGRAMFILES%\Microsoft\Edge\Application\msedge.exe",
        r"%PROGRAMFILES(X86)%\Microsoft\Edge\Application\msedge.exe",
        r"%PROGRAMW6432%\Google\Chrome\Application\chrome.exe",
        r"%PROGRAMW6432%\Microsoft\Edge\Application\msedge.exe",
        r"~\AppData\Local\Google\Chrome\Application\chrome.exe",
        r"~\AppData\Local\Microsoft\Edge\Application\msedge.exe",
    ]

    UNIX_PATHS: List[str] = [
        "/usr/bin/google-chrome",
        "/usr/bin/google-chrome-stable",
        "/usr/bin/chromium",
        "/usr/bin/chromium-browser",
        "/usr/bin/microsoft-edge",
        "/usr/bin/microsoft-edge-stable",
        "/snap/bin/chromium",
        "/snap/bin/google-chrome",
    ]

    MACOS_PATHS: List[str] = [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        "~/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "~/Applications/Chromium.app/Contents/MacOS/Chromium",
        "~/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    ]

    PATH_NAMES: List[str] = [
        "chromium",
        "google-chrome",
        "google-chrome-stable",
        "chrome",
        "msedge",
        "microsoft-edge",
        "edge",
    ]

    @classmethod
    def _is_executable_file(cls, path_str: str) -> bool:
        """Verifies if a path points to an existing executable file."""
        try:
            expanded = os.path.expanduser(os.path.expandvars(path_str))
            p = Path(expanded)
            if p.is_file():
                if os.name == "nt":
                    return p.suffix.lower() in (".exe", ".cmd", ".bat") or os.access(p, os.X_OK)
                return os.access(p, os.X_OK)
        except Exception:
            pass
        return False

    @classmethod
    def find_browser_executable(
        cls, custom_path: Optional[Union[str, Path]] = None
    ) -> Optional[str]:
        """Finds the first available Chromium, Chrome, or Edge executable."""
        # 1. Custom path override
        if custom_path:
            p_str = str(custom_path)
            if cls._is_executable_file(p_str):
                return str(Path(os.path.expanduser(os.path.expandvars(p_str))).resolve())

        # 2. Environment variables
        for var in cls.ENV_VARS:
            val = os.environ.get(var)
            if val and cls._is_executable_file(val):
                return str(Path(os.path.expanduser(os.path.expandvars(val))).resolve())

        # 3. Platform specific candidates
        candidates: List[str] = []
        if os.name == "nt":
            candidates.extend(cls.WINDOWS_PATHS)
        else:
            candidates.extend(cls.UNIX_PATHS)
            candidates.extend(cls.MACOS_PATHS)

        for candidate in candidates:
            if cls._is_executable_file(candidate):
                return str(Path(os.path.expanduser(os.path.expandvars(candidate))).resolve())

        # 4. PATH lookup
        for name in cls.PATH_NAMES:
            found = shutil.which(name)
            if found and cls._is_executable_file(found):
                return str(Path(found).resolve())

        return None

    @classmethod
    def get_available_executables(cls) -> List[str]:
        """Returns all distinct browser executables found on the current system."""
        found_paths: List[str] = []
        seen: Set[str] = set()

        def _add_if_valid(p_str: str) -> None:
            if cls._is_executable_file(p_str):
                resolved = str(Path(os.path.expanduser(os.path.expandvars(p_str))).resolve())
                if resolved not in seen:
                    seen.add(resolved)
                    found_paths.append(resolved)

        for var in cls.ENV_VARS:
            val = os.environ.get(var)
            if val:
                _add_if_valid(val)

        all_candidates = cls.WINDOWS_PATHS + cls.UNIX_PATHS + cls.MACOS_PATHS
        for candidate in all_candidates:
            _add_if_valid(candidate)

        for name in cls.PATH_NAMES:
            which_p = shutil.which(name)
            if which_p:
                _add_if_valid(which_p)

        return found_paths


class ManagedChromiumProcess:
    """Spawns and monitors a Chromium process configured with remote debugging."""

    def __init__(
        self,
        executable_path: Optional[Union[str, Path]] = None,
        port: int = 0,
        headless: Union[bool, str] = "new",
        user_data_dir: Optional[Union[str, Path]] = None,
        window_size: Tuple[int, int] = (1920, 1080),
        extra_args: Optional[Sequence[str]] = None,
        disable_gpu: bool = True,
        startup_timeout_s: float = 15.0,
        auto_cleanup: bool = True,
    ) -> None:
        if executable_path:
            p_str = str(executable_path)
            if not ChromiumDiscovery._is_executable_file(p_str) and not Path(p_str).exists():
                raise FileNotFoundError(f"Specified browser executable not found: {executable_path}")
            self.executable_path = p_str
        else:
            self.executable_path = ChromiumDiscovery.find_browser_executable()
            if not self.executable_path:
                raise FileNotFoundError(
                    "No Chromium, Chrome, or Edge executable found. "
                    "Specify executable_path or set CHROMIUM_PATH environment variable."
                )

        self.requested_port = port
        self.headless = headless
        self.window_size = window_size
        self.extra_args = list(extra_args or [])
        self.disable_gpu = disable_gpu
        self.startup_timeout_s = startup_timeout_s
        self.auto_cleanup = auto_cleanup

        self._created_temp_dir = False
        if user_data_dir is not None:
            self.user_data_dir = Path(user_data_dir).resolve()
        else:
            self.user_data_dir = Path(tempfile.mkdtemp(prefix="reflex_chromium_")).resolve()
            self._created_temp_dir = True

        self.process: Optional[subprocess.Popen[bytes]] = None
        self.actual_port: Optional[int] = None
        self.ws_endpoint: Optional[str] = None
        self.http_endpoint: Optional[str] = None

    def _build_command_args(self) -> List[str]:
        """Constructs process argument vector."""
        args: List[str] = [
            self.executable_path,
            f"--remote-debugging-port={self.requested_port}",
            f"--user-data-dir={self.user_data_dir}",
            f"--window-size={self.window_size[0]},{self.window_size[1]}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-background-networking",
            "--disable-background-timer-throttling",
            "--disable-backgrounding-occluded-windows",
            "--disable-breakpad",
            "--disable-client-side-phishing-detection",
            "--disable-default-apps",
            "--disable-dev-shm-usage",
            "--disable-extensions",
            "--disable-features=Translate,OptimizationHints,MediaRouter",
            "--disable-hang-monitor",
            "--disable-popup-blocking",
            "--disable-prompt-on-repost",
            "--disable-sync",
            "--metrics-recording-only",
            "--password-store=basic",
            "--use-mock-keychain",
            "--mute-audio",
            "--hide-scrollbars",
        ]

        if self.disable_gpu:
            args.extend(["--disable-gpu", "--disable-software-rasterizer"])

        if self.headless is True or self.headless == "new":
            args.append("--headless=new")
        elif self.headless == "old" or self.headless == "classic":
            args.append("--headless")
        elif self.headless is False:
            pass

        if self.extra_args:
            args.extend(self.extra_args)

        return args

    def start(self) -> str:
        """Launches the Chromium process and awaits DevTools active port discovery."""
        if self.process is not None and self.is_running():
            assert self.ws_endpoint is not None
            return self.ws_endpoint

        self.user_data_dir.mkdir(parents=True, exist_ok=True)
        active_port_file = self.user_data_dir / "DevToolsActivePort"
        if active_port_file.exists():
            try:
                active_port_file.unlink()
            except Exception:
                pass

        cmd = self._build_command_args()
        self.process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        start_time = time.time()
        while time.time() - start_time < self.startup_timeout_s:
            if self.process.poll() is not None:
                stderr_out = ""
                if self.process.stderr:
                    try:
                        stderr_out = self.process.stderr.read().decode("utf-8", errors="replace")
                    except Exception:
                        pass
                raise RuntimeError(
                    f"Chromium process exited prematurely with returncode {self.process.returncode}: {stderr_out}"
                )

            # Check DevToolsActivePort file
            if active_port_file.exists():
                try:
                    lines = [l.strip() for l in active_port_file.read_text(encoding="utf-8").splitlines() if l.strip()]
                    if len(lines) >= 2 and lines[0].isdigit():
                        port = int(lines[0])
                        path = lines[1]
                        self.actual_port = port
                        self.http_endpoint = f"http://127.0.0.1:{port}"
                        self.ws_endpoint = f"ws://127.0.0.1:{port}{path}"
                        return self.ws_endpoint
                except Exception:
                    pass

            # Fallback: query /json/version if port was explicitly requested
            if self.requested_port != 0:
                try:
                    version_info = self._fetch_http_json(f"http://127.0.0.1:{self.requested_port}/json/version")
                    ws_url = version_info.get("webSocketDebuggerUrl")
                    if ws_url:
                        self.actual_port = self.requested_port
                        self.http_endpoint = f"http://127.0.0.1:{self.requested_port}"
                        self.ws_endpoint = ws_url
                        return self.ws_endpoint
                except Exception:
                    pass

            time.sleep(0.05)

        self.stop()
        raise TimeoutError(
            f"Timed out waiting {self.startup_timeout_s}s for Chromium DevToolsActivePort in {self.user_data_dir}"
        )

    async def start_async(self) -> str:
        """Asynchronous wrapper for start."""
        return await asyncio.to_thread(self.start)

    def _fetch_http_json(self, url: str, timeout_s: float = 3.0) -> Any:
        """Fetches JSON from the local Chromium HTTP endpoint."""
        req = urllib.request.Request(url, headers={"User-Agent": "Reflex-Browser-Driver"})
        with urllib.request.urlopen(req, timeout=timeout_s) as response:
            return json.loads(response.read().decode("utf-8"))

    def get_version_info(self) -> Dict[str, Any]:
        """Retrieves browser version and protocol metadata via /json/version."""
        if not self.actual_port:
            raise RuntimeError("Chromium process is not active or port is not resolved")
        return self._fetch_http_json(f"http://127.0.0.1:{self.actual_port}/json/version")

    def get_targets(self) -> List[Dict[str, Any]]:
        """Retrieves list of active target pages via /json/list."""
        if not self.actual_port:
            raise RuntimeError("Chromium process is not active or port is not resolved")
        return self._fetch_http_json(f"http://127.0.0.1:{self.actual_port}/json/list")

    def is_running(self) -> bool:
        """Checks whether the underlying process is currently running."""
        return self.process is not None and self.process.poll() is None

    def check_health(self) -> bool:
        """Verifies process is alive and HTTP DevTools endpoint responds."""
        if not self.is_running() or not self.actual_port:
            return False
        try:
            info = self.get_version_info()
            return bool(info.get("webSocketDebuggerUrl"))
        except Exception:
            return False

    def stop(self) -> None:
        """Gracefully terminates Chromium and cleans up the temporary profile."""
        if self.process is not None:
            if self.process.stdout:
                try:
                    self.process.stdout.close()
                except Exception:
                    pass
            if self.process.stderr:
                try:
                    self.process.stderr.close()
                except Exception:
                    pass
            if self.process.poll() is None:
                try:
                    self.process.terminate()
                    self.process.wait(timeout=3.0)
                except (subprocess.TimeoutExpired, Exception):
                    try:
                        self.process.kill()
                        self.process.wait(timeout=2.0)
                    except Exception:
                        pass
            self.process = None

        if self.auto_cleanup and self._created_temp_dir and self.user_data_dir.exists():
            for _ in range(5):
                try:
                    shutil.rmtree(self.user_data_dir, ignore_errors=False)
                    break
                except Exception:
                    time.sleep(0.1)
            if self.user_data_dir.exists():
                shutil.rmtree(self.user_data_dir, ignore_errors=True)

    async def stop_async(self) -> None:
        """Asynchronous wrapper for stop."""
        await asyncio.to_thread(self.stop)

    def close(self) -> None:
        """Alias for stop."""
        self.stop()

    def __enter__(self) -> ManagedChromiumProcess:
        self.start()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.stop()

    async def __aenter__(self) -> ManagedChromiumProcess:
        await self.start_async()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.stop_async()

    def __del__(self) -> None:
        try:
            self.stop()
        except Exception:
            pass


class CDPWebSocketClient(CDPSessionProtocol):
    """Direct WebSocket client for sending CDP commands and receiving events."""

    def __init__(
        self,
        ws_url: str,
        session_id: Optional[str] = None,
        timeout: float = 30.0,
    ) -> None:
        self.ws_url = ws_url
        self.session_id = session_id
        self.default_timeout = timeout

        self._ws: Optional[websockets.WebSocketClientProtocol] = None
        self._id_counter: int = 0
        self._pending_requests: Dict[int, asyncio.Future[Dict[str, Any]]] = {}
        self._event_listeners: Dict[str, List[Callable[[Dict[str, Any]], Any]]] = {}
        self._listener_task: Optional[asyncio.Task[None]] = None
        self._is_closed: bool = False
        self._child_sessions: Dict[str, CDPChildSession] = {}

    @property
    def is_connected(self) -> bool:
        """Returns True if WebSocket is active and not closed."""
        return self._ws is not None and not self._is_closed

    async def connect(self) -> CDPWebSocketClient:
        """Connects to the DevTools WebSocket endpoint and starts the receive loop."""
        if self._ws is not None and not self._is_closed:
            return self

        self._ws = await websockets.connect(
            self.ws_url,
            max_size=32 * 1024 * 1024,  # 32MB buffer for large DOM/screenshots
            ping_interval=None,
        )
        self._is_closed = False
        self._listener_task = asyncio.create_task(self._listen_loop())
        return self

    async def _listen_loop(self) -> None:
        """Background receiver dispatching responses and events."""
        assert self._ws is not None
        try:
            async for raw_msg in self._ws:
                try:
                    msg = json.loads(raw_msg)
                except Exception:
                    continue

                # 1. Responses to commands
                if "id" in msg:
                    req_id = msg["id"]
                    fut = self._pending_requests.pop(req_id, None)
                    if fut is not None and not fut.done():
                        if "error" in msg:
                            err_info = msg["error"]
                            fut.set_exception(
                                CDPError(
                                    message=err_info.get("message", "Unknown CDP error"),
                                    code=err_info.get("code"),
                                    data=err_info.get("data"),
                                )
                            )
                        else:
                            fut.set_result(msg.get("result", {}))

                # 2. Event notifications
                elif "method" in msg:
                    method = msg["method"]
                    params = msg.get("params", {})
                    session_id = msg.get("sessionId")

                    if session_id and session_id in self._child_sessions:
                        self._child_sessions[session_id]._dispatch_event(method, params)
                    else:
                        self._dispatch_event(method, params)

        except (websockets.ConnectionClosed, asyncio.CancelledError):
            pass
        finally:
            # Drain and fail any pending requests
            for req_id, fut in list(self._pending_requests.items()):
                if not fut.done():
                    fut.set_exception(CDPConnectionClosedError())
            self._pending_requests.clear()

    async def send(
        self,
        method: str,
        params: Optional[Dict[str, Any]] = None,
        timeout: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Sends a CDP command and awaits its correlated response."""
        if self._ws is None or self._is_closed:
            raise CDPConnectionClosedError("Cannot send command: WebSocket client is not connected")

        self._id_counter += 1
        req_id = self._id_counter
        loop = asyncio.get_running_loop()
        fut: asyncio.Future[Dict[str, Any]] = loop.create_future()
        self._pending_requests[req_id] = fut

        payload: Dict[str, Any] = {
            "id": req_id,
            "method": method,
        }
        if params is not None:
            payload["params"] = params
        if self.session_id is not None:
            payload["sessionId"] = self.session_id

        await self._ws.send(json.dumps(payload))

        effective_timeout = timeout if timeout is not None else self.default_timeout
        try:
            if effective_timeout is not None and effective_timeout > 0:
                return await asyncio.wait_for(fut, timeout=effective_timeout)
            return await fut
        except asyncio.TimeoutError:
            self._pending_requests.pop(req_id, None)
            raise TimeoutError(f"CDP command '{method}' (id={req_id}) timed out after {effective_timeout}s")

    def on(self, event: str, callback: Callable[[Dict[str, Any]], Any]) -> None:
        """Alias for add_event_listener."""
        self.add_event_listener(event, callback)

    def add_event_listener(self, event: str, callback: Callable[[Dict[str, Any]], Any]) -> None:
        """Registers a callback for CDP event notifications."""
        self._event_listeners.setdefault(event, []).append(callback)

    def remove_event_listener(self, event: str, callback: Callable[[Dict[str, Any]], Any]) -> None:
        """Removes a registered callback."""
        if event in self._event_listeners:
            self._event_listeners[event] = [cb for cb in self._event_listeners[event] if cb != callback]

    def _dispatch_event(self, event: str, params: Dict[str, Any]) -> None:
        """Dispatches event to matching and wildcard listeners."""
        callbacks = list(self._event_listeners.get(event, []))
        callbacks.extend(self._event_listeners.get("*", []))

        for cb in callbacks:
            try:
                res = cb(params)
                if asyncio.iscoroutine(res):
                    asyncio.create_task(res)
            except Exception:
                pass

    async def wait_for_event(
        self,
        event: str,
        timeout: float = 10.0,
        predicate: Optional[Callable[[Dict[str, Any]], bool]] = None,
    ) -> Dict[str, Any]:
        """Awaits a specific event matching an optional predicate."""
        loop = asyncio.get_running_loop()
        fut: asyncio.Future[Dict[str, Any]] = loop.create_future()

        def _handler(params: Dict[str, Any]) -> None:
            if not fut.done():
                if predicate is None or predicate(params):
                    fut.set_result(params)

        self.add_event_listener(event, _handler)
        try:
            return await asyncio.wait_for(fut, timeout=timeout)
        finally:
            self.remove_event_listener(event, _handler)

    def create_session(self, session_id: str) -> CDPChildSession:
        """Returns a child session tied to a specific CDP target sessionId."""
        child = CDPChildSession(parent_client=self, session_id=session_id)
        self._child_sessions[session_id] = child
        return child

    async def close(self) -> None:
        """Closes WebSocket connection and cancels listener task."""
        self._is_closed = True
        if self._listener_task and not self._listener_task.done():
            self._listener_task.cancel()
        if self._ws is not None:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None

    async def __aenter__(self) -> CDPWebSocketClient:
        return await self.connect()

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.close()


class CDPChildSession(CDPSessionProtocol):
    """Sub-session multiplexed over a root CDP WebSocket connection using sessionId."""

    def __init__(self, parent_client: CDPWebSocketClient, session_id: str) -> None:
        self.parent_client = parent_client
        self.session_id = session_id
        self._event_listeners: Dict[str, List[Callable[[Dict[str, Any]], Any]]] = {}

    async def send(
        self,
        method: str,
        params: Optional[Dict[str, Any]] = None,
        timeout: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Sends command with this session's sessionId."""
        if not self.parent_client.is_connected:
            raise CDPConnectionClosedError("Parent CDP client is disconnected")

        self.parent_client._id_counter += 1
        req_id = self.parent_client._id_counter
        loop = asyncio.get_running_loop()
        fut: asyncio.Future[Dict[str, Any]] = loop.create_future()
        self.parent_client._pending_requests[req_id] = fut

        payload: Dict[str, Any] = {
            "id": req_id,
            "method": method,
            "sessionId": self.session_id,
        }
        if params is not None:
            payload["params"] = params

        assert self.parent_client._ws is not None
        await self.parent_client._ws.send(json.dumps(payload))

        effective_timeout = timeout if timeout is not None else self.parent_client.default_timeout
        try:
            if effective_timeout is not None and effective_timeout > 0:
                return await asyncio.wait_for(fut, timeout=effective_timeout)
            return await fut
        except asyncio.TimeoutError:
            self.parent_client._pending_requests.pop(req_id, None)
            raise TimeoutError(f"Child session command '{method}' timed out after {effective_timeout}s")

    def on(self, event: str, callback: Callable[[Dict[str, Any]], Any]) -> None:
        self.add_event_listener(event, callback)

    def add_event_listener(self, event: str, callback: Callable[[Dict[str, Any]], Any]) -> None:
        self._event_listeners.setdefault(event, []).append(callback)

    def remove_event_listener(self, event: str, callback: Callable[[Dict[str, Any]], Any]) -> None:
        if event in self._event_listeners:
            self._event_listeners[event] = [cb for cb in self._event_listeners[event] if cb != callback]

    def _dispatch_event(self, event: str, params: Dict[str, Any]) -> None:
        callbacks = list(self._event_listeners.get(event, []))
        callbacks.extend(self._event_listeners.get("*", []))
        for cb in callbacks:
            try:
                res = cb(params)
                if asyncio.iscoroutine(res):
                    asyncio.create_task(res)
            except Exception:
                pass


class CDPMouse:
    """Dispatches low-level mouse events via CDP Input domain."""

    def __init__(self, cdp_session: CDPSessionProtocol) -> None:
        self.cdp = cdp_session
        self._x: int = 0
        self._y: int = 0

    async def move(self, x: int, y: int) -> None:
        """Dispatches mouseMoved event."""
        self._x, self._y = int(x), int(y)
        await self.cdp.send(
            "Input.dispatchMouseEvent",
            {"type": "mouseMoved", "x": self._x, "y": self._y},
        )

    async def down(self, button: str = "left", click_count: int = 1) -> None:
        """Dispatches mousePressed event."""
        btn = "right" if button.lower() == "right" else ("middle" if button.lower() == "middle" else "left")
        await self.cdp.send(
            "Input.dispatchMouseEvent",
            {"type": "mousePressed", "x": self._x, "y": self._y, "button": btn, "clickCount": click_count},
        )

    async def up(self, button: str = "left", click_count: int = 1) -> None:
        """Dispatches mouseReleased event."""
        btn = "right" if button.lower() == "right" else ("middle" if button.lower() == "middle" else "left")
        await self.cdp.send(
            "Input.dispatchMouseEvent",
            {"type": "mouseReleased", "x": self._x, "y": self._y, "button": btn, "clickCount": click_count},
        )

    async def click(self, x: int, y: int, button: str = "left") -> None:
        """Moves to coordinates and triggers full click sequence."""
        await self.move(x, y)
        await self.down(button=button, click_count=1)
        await self.up(button=button, click_count=1)

    async def dblclick(self, x: int, y: int, button: str = "left") -> None:
        """Triggers double click sequence."""
        await self.move(x, y)
        await self.down(button=button, click_count=1)
        await self.up(button=button, click_count=1)
        await self.down(button=button, click_count=2)
        await self.up(button=button, click_count=2)

    async def wheel(self, delta_x: int, delta_y: int, x: Optional[int] = None, y: Optional[int] = None) -> None:
        """Dispatches mouseWheel event."""
        px = int(x) if x is not None else self._x
        py = int(y) if y is not None else self._y
        await self.cdp.send(
            "Input.dispatchMouseEvent",
            {"type": "mouseWheel", "x": px, "y": py, "deltaX": int(delta_x), "deltaY": int(delta_y)},
        )


class CDPKeyboard:
    """Dispatches key events and text insertion via CDP Input domain."""

    KEY_CODES: Dict[str, Dict[str, Any]] = {
        "Enter": {"windowsVirtualKeyCode": 13, "code": "Enter", "key": "Enter", "text": "\r"},
        "Tab": {"windowsVirtualKeyCode": 9, "code": "Tab", "key": "Tab"},
        "Backspace": {"windowsVirtualKeyCode": 8, "code": "Backspace", "key": "Backspace"},
        "Escape": {"windowsVirtualKeyCode": 27, "code": "Escape", "key": "Escape"},
        "ArrowDown": {"windowsVirtualKeyCode": 40, "code": "ArrowDown", "key": "ArrowDown"},
        "ArrowUp": {"windowsVirtualKeyCode": 38, "code": "ArrowUp", "key": "ArrowUp"},
        "ArrowLeft": {"windowsVirtualKeyCode": 37, "code": "ArrowLeft", "key": "ArrowLeft"},
        "ArrowRight": {"windowsVirtualKeyCode": 39, "code": "ArrowRight", "key": "ArrowRight"},
        "Delete": {"windowsVirtualKeyCode": 46, "code": "Delete", "key": "Delete"},
        "Home": {"windowsVirtualKeyCode": 36, "code": "Home", "key": "Home"},
        "End": {"windowsVirtualKeyCode": 35, "code": "End", "key": "End"},
        "PageUp": {"windowsVirtualKeyCode": 33, "code": "PageUp", "key": "PageUp"},
        "PageDown": {"windowsVirtualKeyCode": 34, "code": "PageDown", "key": "PageDown"},
        " ": {"windowsVirtualKeyCode": 32, "code": "Space", "key": " ", "text": " "},
        "Space": {"windowsVirtualKeyCode": 32, "code": "Space", "key": " ", "text": " "},
    }

    def __init__(self, cdp_session: CDPSessionProtocol) -> None:
        self.cdp = cdp_session

    async def type(self, text: str) -> None:
        """Types string into currently focused element via CDP insertText."""
        if not text:
            return
        await self.cdp.send("Input.insertText", {"text": text})

    async def press(self, key: str) -> None:
        """Dispatches key press (down + up) for a named key or character."""
        key_def = self.KEY_CODES.get(key)
        if key_def:
            down_params: Dict[str, Any] = {"type": "rawKeyDown", **key_def}
            up_params: Dict[str, Any] = {"type": "keyUp", "code": key_def.get("code", key), "key": key_def.get("key", key)}
            await self.cdp.send("Input.dispatchKeyEvent", down_params)
            if "text" in key_def:
                await self.cdp.send("Input.dispatchKeyEvent", {"type": "char", "text": key_def["text"]})
            await self.cdp.send("Input.dispatchKeyEvent", up_params)
        else:
            # Single character key press
            await self.cdp.send("Input.dispatchKeyEvent", {"type": "keyDown", "text": key, "key": key})
            await self.cdp.send("Input.dispatchKeyEvent", {"type": "keyUp", "text": key, "key": key})


class CDPLocator:
    """Provides element-level targeting and actions over CDP."""

    def __init__(self, page: CDPPage, selector: str) -> None:
        self.page = page
        self.selector = selector

    def _build_js_resolver(self) -> str:
        """Generates JS expression that resolves standard CSS, text, and XPath selectors."""
        return f"""
        (() => {{
            const sel = {json.dumps(self.selector)};
            if (sel.startsWith('xpath=') || sel.startsWith('//')) {{
                const xp = sel.startsWith('xpath=') ? sel.substring(6) : sel;
                const r = document.evaluate(xp, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null);
                return r.singleNodeValue;
            }}
            if (sel.startsWith('text=')) {{
                const t = sel.substring(5).replace(/^["']|["']$/g, '');
                const all = Array.from(document.querySelectorAll('*'));
                for (const el of all) {{
                    if (el.children.length === 0 && (el.innerText || el.textContent || '').trim() === t) return el;
                }}
                for (const el of all) {{
                    if ((el.innerText || el.textContent || '').includes(t)) return el;
                }}
                return null;
            }}
            if (sel.startsWith('#')) return document.querySelector(sel);
            return document.querySelector(sel) || document.getElementById(sel);
        }})()
        """

    async def get_bounding_rect(self) -> Optional[Dict[str, float]]:
        """Queries the element's bounding client rect via Runtime.evaluate."""
        expr = f"""
        (() => {{
            const el = {self._build_js_resolver()};
            if (!el) return null;
            const r = el.getBoundingClientRect();
            return {{
                x: r.left,
                y: r.top,
                width: r.width,
                height: r.height,
                cx: r.left + r.width / 2,
                cy: r.top + r.height / 2,
            }};
        }})()
        """
        return await self.page.evaluate(expr)

    async def scroll_into_view_if_needed(self) -> None:
        """Scrolls element into view."""
        expr = f"""
        (() => {{
            const el = {self._build_js_resolver()};
            if (el && el.scrollIntoView) {{
                el.scrollIntoView({{ block: 'center', inline: 'center', behavior: 'instant' }});
            }}
        }})()
        """
        await self.page.evaluate(expr)

    async def click(self, button: str = "left", force: bool = False) -> None:
        """Clicks the element."""
        await self.scroll_into_view_if_needed()
        rect = await self.get_bounding_rect()
        if rect and rect.get("width", 0) > 0 and rect.get("height", 0) > 0 and not force:
            await self.page.mouse.click(int(rect["cx"]), int(rect["cy"]), button=button)
        else:
            # Direct DOM dispatch
            expr = f"""
            (() => {{
                const el = {self._build_js_resolver()};
                if (!el) throw new Error('Element not found for click: ' + {json.dumps(self.selector)});
                el.focus();
                el.click();
            }})()
            """
            await self.page.evaluate(expr)

    async def dblclick(self, force: bool = False) -> None:
        """Double-clicks the element."""
        await self.scroll_into_view_if_needed()
        rect = await self.get_bounding_rect()
        if rect and not force:
            await self.page.mouse.dblclick(int(rect["cx"]), int(rect["cy"]))
        else:
            await self.click(force=True)
            await self.click(force=True)

    async def fill(self, text: str) -> None:
        """Sets element value and fires input & change events."""
        expr = f"""
        (() => {{
            const el = {self._build_js_resolver()};
            if (!el) throw new Error('Element not found for fill: ' + {json.dumps(self.selector)});
            el.focus();
            el.value = {json.dumps(text)};
            el.dispatchEvent(new Event('input', {{ bubbles: true }}));
            el.dispatchEvent(new Event('change', {{ bubbles: true }}));
        }})()
        """
        await self.page.evaluate(expr)

    async def type(self, text: str) -> None:
        """Focuses element and types text."""
        expr = f"""
        (() => {{
            const el = {self._build_js_resolver()};
            if (el) el.focus();
        }})()
        """
        await self.page.evaluate(expr)
        await self.page.keyboard.type(text)

    async def press(self, key: str) -> None:
        """Focuses element and presses key."""
        expr = f"""
        (() => {{
            const el = {self._build_js_resolver()};
            if (el) el.focus();
        }})()
        """
        await self.page.evaluate(expr)
        await self.page.keyboard.press(key)

    async def hover(self) -> None:
        """Hovers over the element center."""
        await self.scroll_into_view_if_needed()
        rect = await self.get_bounding_rect()
        if rect:
            await self.page.mouse.move(int(rect["cx"]), int(rect["cy"]))

    async def drag_to(self, target: Union[CDPLocator, str]) -> None:
        """Drags from this element to a target element."""
        target_loc = target if isinstance(target, CDPLocator) else self.page.locator(target)
        await self.scroll_into_view_if_needed()
        await target_loc.scroll_into_view_if_needed()

        r1 = await self.get_bounding_rect()
        r2 = await target_loc.get_bounding_rect()
        if not r1 or not r2:
            raise RuntimeError("Cannot drag: source or target bounding box unavailable")

        await self.page.mouse.move(int(r1["cx"]), int(r1["cy"]))
        await self.page.mouse.down()
        await self.page.mouse.move(int(r2["cx"]), int(r2["cy"]))
        await self.page.mouse.up()


class CDPPage:
    """High-level page handle offering Playwright-compatible operations over direct CDP."""

    def __init__(
        self,
        cdp_session: CDPSessionProtocol,
        viewport_size: Tuple[int, int] = (1920, 1080),
        target_id: Optional[str] = None,
    ) -> None:
        self.cdp_session = cdp_session
        self._requested_viewport_size = viewport_size
        self._observed_viewport_size: Optional[Tuple[int, int]] = None
        reported = getattr(cdp_session, "viewport_size", None)
        if (
            isinstance(reported, (tuple, list))
            and len(reported) == 2
            and all(isinstance(v, (int, float)) for v in reported)
        ):
            self._observed_viewport_size = (int(reported[0]), int(reported[1]))
        self.target_id = target_id
        self.mouse = CDPMouse(self.cdp_session)
        self.keyboard = CDPKeyboard(self.cdp_session)

    @property
    def viewport_size(self) -> Dict[str, int]:
        """Returns viewport dimensions dictionary.

        Observed target geometry always wins over the requested launch size:
        the constructor argument is a window-size hint, while the session
        report and per-capture observed pixels describe the live target that
        coordinate grounding must use.
        """
        width, height = self._observed_viewport_size or self._requested_viewport_size
        return {"width": width, "height": height}

    @property
    def requested_viewport_size(self) -> Tuple[int, int]:
        """Launch-requested size, retained for provenance."""
        return self._requested_viewport_size

    def update_observed_viewport(self, width: int, height: int) -> None:
        """Records captured pixel dimensions as the grounding geometry."""
        self._observed_viewport_size = (int(width), int(height))

    def locator(self, selector: str) -> CDPLocator:
        """Returns a CDPLocator for the selector."""
        return CDPLocator(self, selector)

    def get_by_text(self, text: str) -> CDPLocator:
        """Returns a CDPLocator targeting text content."""
        return CDPLocator(self, f"text={text}")

    async def evaluate(self, expression: str) -> Any:
        """Evaluates JavaScript expression in the page context."""
        expr = expression.strip()
        # If expression is an uninvoked arrow function or function declaration, wrap and invoke it
        if (expr.startswith("() =>") or expr.startswith("async () =>") or expr.startswith("function")) and not expr.endswith("()"):
            expr = f"({expr})()"

        resp = await self.cdp_session.send(
            "Runtime.evaluate",
            {
                "expression": expr,
                "returnByValue": True,
                "awaitPromise": True,
            },
        )
        result = resp.get("result", {})
        if result.get("subtype") == "error":
            desc = result.get("description", "Evaluation failed")
            raise RuntimeError(f"CDP JavaScript evaluation error: {desc}")
        return result.get("value")

    async def goto(self, url: str, wait_until: str = "load", timeout_ms: float = 30000.0) -> Dict[str, Any]:
        """Navigates to URL and optionally awaits load completion."""
        wait_event = "Page.loadEventFired" if wait_until == "load" else "Page.domContentEventFired"

        event_task: Optional[asyncio.Task[Dict[str, Any]]] = None
        if isinstance(self.cdp_session, CDPWebSocketClient):
            event_task = asyncio.create_task(
                self.cdp_session.wait_for_event(wait_event, timeout=timeout_ms / 1000.0)
            )

        resp = await self.cdp_session.send("Page.navigate", {"url": url})

        if event_task is not None:
            try:
                await event_task
            except (asyncio.TimeoutError, Exception):
                pass

        return resp

    async def screenshot(self, type: str = "png") -> bytes:
        """Captures page screenshot as bytes."""
        resp = await self.cdp_session.send("Page.captureScreenshot", {"format": type})
        b64_data = resp.get("data", "")
        return base64.b64decode(b64_data)

    async def content(self) -> str:
        """Returns the full HTML document string."""
        return str(await self.evaluate("document.documentElement.outerHTML") or "")

    async def wait_for_timeout(self, duration_ms: float) -> None:
        """Asynchronously waits for duration_ms."""
        await asyncio.sleep(duration_ms / 1000.0)

    async def drag_and_drop(self, source: str, target: str) -> None:
        """Performs drag and drop from source selector to target selector."""
        loc1 = self.locator(source)
        loc2 = self.locator(target)
        await loc1.drag_to(loc2)


class ManagedChromiumSession:
    """Async context manager managing Chromium process, CDP connection, observation, and actions."""

    def __init__(
        self,
        executable_path: Optional[Union[str, Path]] = None,
        port: int = 0,
        headless: Union[bool, str] = "new",
        window_size: Tuple[int, int] = (1920, 1080),
        extra_args: Optional[Sequence[str]] = None,
        user_data_dir: Optional[Union[str, Path]] = None,
        disable_gpu: bool = True,
        startup_timeout_s: float = 15.0,
        auto_cleanup: bool = True,
        prefer_js_distiller: bool = True,
    ) -> None:
        self.executable_path = executable_path
        self.port = port
        self.headless = headless
        self.window_size = window_size
        self.extra_args = extra_args
        self.user_data_dir = user_data_dir
        self.disable_gpu = disable_gpu
        self.startup_timeout_s = startup_timeout_s
        self.auto_cleanup = auto_cleanup
        self.prefer_js_distiller = prefer_js_distiller

        self.process: Optional[ManagedChromiumProcess] = None
        self.browser_cdp: Optional[CDPWebSocketClient] = None
        self.page_cdp: Optional[CDPWebSocketClient] = None
        self.page: Optional[CDPPage] = None
        self.observation_provider: Optional[CDPObservationProvider] = None
        self.action_adapter: Optional[CDPActionAdapter] = None

    async def start(self) -> ManagedChromiumSession:
        """Launches Chromium, initializes CDP WebSocket clients, and enables core domains."""
        # 1. Spawn Chromium
        self.process = ManagedChromiumProcess(
            executable_path=self.executable_path,
            port=self.port,
            headless=self.headless,
            user_data_dir=self.user_data_dir,
            window_size=self.window_size,
            extra_args=self.extra_args,
            disable_gpu=self.disable_gpu,
            startup_timeout_s=self.startup_timeout_s,
            auto_cleanup=self.auto_cleanup,
        )
        browser_ws_url = await self.process.start_async()

        # 2. Connect Browser CDP client
        self.browser_cdp = CDPWebSocketClient(browser_ws_url)
        await self.browser_cdp.connect()

        # 3. Locate or create default page target
        targets = self.process.get_targets()
        page_target = next((t for t in targets if t.get("type") == "page"), None)

        if page_target and page_target.get("webSocketDebuggerUrl"):
            page_ws_url = page_target["webSocketDebuggerUrl"]
        else:
            create_resp = await self.browser_cdp.send("Target.createTarget", {"url": "about:blank"})
            target_id = create_resp.get("targetId", "")
            targets = self.process.get_targets()
            page_target = next((t for t in targets if t.get("id") == target_id or t.get("type") == "page"), None)
            assert page_target and page_target.get("webSocketDebuggerUrl")
            page_ws_url = page_target["webSocketDebuggerUrl"]

        # 4. Connect Page CDP client
        self.page_cdp = CDPWebSocketClient(page_ws_url)
        await self.page_cdp.connect()

        # 5. Enable core CDP domains on page
        await self.page_cdp.send("Page.enable")
        await self.page_cdp.send("DOM.enable")
        await self.page_cdp.send("Accessibility.enable")
        await self.page_cdp.send("Runtime.enable")
        await self.page_cdp.send("Network.enable")

        # 6. Instantiate Page, Observation Provider, and Action Adapter
        self.page = CDPPage(
            cdp_session=self.page_cdp,
            viewport_size=self.window_size,
            target_id=page_target.get("id"),
        )
        self.observation_provider = CDPObservationProvider(
            cdp_session=self.page_cdp,
            page=self.page,
            viewport_size=self.window_size,
            prefer_js_distiller=self.prefer_js_distiller,
        )
        self.action_adapter = CDPActionAdapter(
            page=self.page,
            cdp_session=self.page_cdp,
        )

        return self

    async def navigate(self, url: str, wait_until: str = "load", timeout_ms: float = 30000.0) -> Dict[str, Any]:
        """Navigates page to URL."""
        if not self.page:
            raise RuntimeError("ManagedChromiumSession is not active")
        return await self.page.goto(url, wait_until=wait_until, timeout_ms=timeout_ms)

    async def evaluate(self, expression: str) -> Any:
        """Evaluates JavaScript expression in the active page."""
        if not self.page:
            raise RuntimeError("ManagedChromiumSession is not active")
        return await self.page.evaluate(expression)

    async def capture_state(self) -> CanonicalUIGraph:
        """Captures CanonicalUIGraph representation via CDPObservationProvider."""
        if not self.observation_provider:
            raise RuntimeError("ManagedChromiumSession is not active")
        return await self.observation_provider.capture_state()

    async def capture_screenshot(self) -> bytes:
        """Captures viewport screenshot bytes."""
        if not self.observation_provider:
            raise RuntimeError("ManagedChromiumSession is not active")
        return await self.observation_provider.capture_screenshot()

    async def get_page_content(self) -> str:
        """Retrieves outer HTML of page."""
        if not self.page:
            raise RuntimeError("ManagedChromiumSession is not active")
        return await self.page.content()

    async def close(self) -> None:
        """Closes CDP WebSocket clients and terminates Chromium process."""
        if self.page_cdp:
            try:
                await self.page_cdp.close()
            except Exception:
                pass
            self.page_cdp = None

        if self.browser_cdp:
            try:
                await self.browser_cdp.close()
            except Exception:
                pass
            self.browser_cdp = None

        if self.process:
            try:
                await self.process.stop_async()
            except Exception:
                pass
            self.process = None

    async def __aenter__(self) -> ManagedChromiumSession:
        return await self.start()

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.close()
