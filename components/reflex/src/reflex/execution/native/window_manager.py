"""Reflex Native Window Manager for deterministic desktop window manipulation.

Enables instant window discovery, focusing, resizing, and tiling (e.g. organizing
multiple Notepad or application windows across screen grids) without fragile mouse drags.
Provides a native Win32 implementation on Windows and a high-fidelity mock substrate
for testing and cross-platform execution.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
import math
import os
import re
import shlex
import subprocess
import sys
import time
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple, Union


@dataclass(frozen=True)
class WindowInfo:
    """Descriptor for a native operating system window."""

    handle: int
    title: str
    process_name: str
    x: int
    y: int
    width: int
    height: int
    is_minimized: bool = False
    is_maximized: bool = False
    is_visible: bool = True

    @property
    def bounds(self) -> Tuple[int, int, int, int]:
        return (self.x, self.y, self.width, self.height)

    def display_line(self) -> str:
        """One-line human-readable window descriptor (legacy HWND format)."""
        return (
            f"[HWND {self.handle}] '{self.title}' ({self.process_name}) "
            f"{self.width}x{self.height} at ({self.x},{self.y})"
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "handle": self.handle,
            "title": self.title,
            "process_name": self.process_name,
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
            "is_minimized": self.is_minimized,
            "is_maximized": self.is_maximized,
            "is_visible": self.is_visible,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> WindowInfo:
        return cls(
            handle=int(data["handle"]),
            title=str(data.get("title", "")),
            process_name=str(data.get("process_name", "")),
            x=int(data.get("x", 0)),
            y=int(data.get("y", 0)),
            width=int(data.get("width", 800)),
            height=int(data.get("height", 600)),
            is_minimized=bool(data.get("is_minimized", False)),
            is_maximized=bool(data.get("is_maximized", False)),
            is_visible=bool(data.get("is_visible", True)),
        )


@dataclass
class MockWindowManagerSubstrate:
    """In-memory mock window substrate for Linux, WSL, CI, and deterministic testing."""

    windows: Dict[int, Dict[str, Any]] = field(default_factory=dict)
    focused_handle: Optional[int] = None
    next_handle: int = 1000
    events: List[Dict[str, Any]] = field(default_factory=list)

    def add_window(
        self,
        title: str,
        process_name: str = "notepad.exe",
        x: int = 50,
        y: int = 50,
        width: int = 600,
        height: int = 400,
        handle: Optional[int] = None,
        is_minimized: bool = False,
        is_maximized: bool = False,
        is_visible: bool = True,
    ) -> int:
        h = handle or self.next_handle
        self.next_handle = max(self.next_handle + 1, h + 1)
        self.windows[h] = {
            "handle": h,
            "title": title,
            "process_name": process_name,
            "x": x,
            "y": y,
            "width": width,
            "height": height,
            "is_minimized": is_minimized,
            "is_maximized": is_maximized,
            "is_visible": is_visible,
        }
        if self.focused_handle is None:
            self.focused_handle = h
        self.events.append({"type": "add_window", "handle": h, "title": title})
        return h

    def list_windows(self) -> List[Dict[str, Any]]:
        return list(self.windows.values())

    def set_bounds(self, handle: int, x: int, y: int, width: int, height: int) -> bool:
        if handle in self.windows:
            self.windows[handle]["x"] = x
            self.windows[handle]["y"] = y
            self.windows[handle]["width"] = width
            self.windows[handle]["height"] = height
            self.windows[handle]["is_minimized"] = False
            self.events.append(
                {"type": "set_bounds", "handle": handle, "x": x, "y": y, "width": width, "height": height}
            )
            return True
        return False

    def focus_window(self, handle: int) -> bool:
        if handle in self.windows:
            self.focused_handle = handle
            self.events.append({"type": "focus_window", "handle": handle})
            return True
        return False

    def minimize_window(self, handle: int) -> bool:
        if handle in self.windows:
            self.windows[handle]["is_minimized"] = True
            self.events.append({"type": "minimize_window", "handle": handle})
            return True
        return False

    def maximize_window(self, handle: int) -> bool:
        if handle in self.windows:
            self.windows[handle]["is_maximized"] = True
            self.windows[handle]["is_minimized"] = False
            self.events.append({"type": "maximize_window", "handle": handle})
            return True
        return False

    def restore_window(self, handle: int) -> bool:
        if handle in self.windows:
            self.windows[handle]["is_minimized"] = False
            self.windows[handle]["is_maximized"] = False
            self.events.append({"type": "restore_window", "handle": handle})
            return True
        return False

    def close_window(self, handle: int) -> bool:
        if handle in self.windows:
            del self.windows[handle]
            if self.focused_handle == handle:
                self.focused_handle = next(iter(self.windows.keys())) if self.windows else None
            self.events.append({"type": "close_window", "handle": handle})
            return True
        return False


@dataclass(frozen=True)
class AppLaunchSpec:
    """One app-launch vocabulary entry: request match terms plus launch identity.

    `filter_terms`/`filter_token` drive tiling process-filter resolution, which
    uses slightly different groupings than launch matching (legacy behavior).
    """

    key: str
    match_terms: Tuple[str, ...]
    command: str
    window_title: str
    process_name: str
    filter_terms: Tuple[str, ...] = ()
    filter_token: Optional[str] = None


APP_LAUNCH_TABLE: Tuple[AppLaunchSpec, ...] = (
    AppLaunchSpec("notepad", ("notepad",), "notepad.exe", "Untitled - Notepad", "notepad.exe",
                  ("notepad",), "notepad"),
    AppLaunchSpec("chrome", ("browser", "chrome", "web"), "start chrome", "Google Chrome", "chrome.exe",
                  ("browser", "chrome"), "chrome"),
    AppLaunchSpec("edge", ("edge",), "start msedge", "Microsoft Edge", "msedge.exe",
                  ("edge",), "chrome"),
    AppLaunchSpec("calc", ("calc",), "calc.exe", "Calculator", "calc.exe",
                  ("calc",), "calc"),
    AppLaunchSpec("cmd", ("cmd", "terminal", "powershell"), "cmd.exe", "Command Prompt", "cmd.exe"),
)
"""Ordered app-launch vocabulary (adapter-owned platform knowledge).

Content is verbatim the legacy Jarvis allowlist. Order is significant: the
first entry with any match term contained in the request wins.
"""

APP_ROUTING_TERMS: Tuple[str, ...] = (
    "notepad",
    "browser",
    "chrome",
    "edge",
    "firefox",
    "calc",
    "calculator",
    "terminal",
    "cmd",
    "powershell",
    "wordpad",
    "explorer",
)
"""Verbatim legacy launch-routing vocabulary.

Intentionally NOT derived from APP_LAUNCH_TABLE: "web" is launch-only (it
matches at launch but never routes), while "firefox"/"wordpad"/"explorer"
are route-only (they route, then are denied at launch with the allowlist
message) and "calculator" is redundant with "calc". Preserved exactly.
"""

DEFAULT_APP_KEY = "notepad"
"""Default app key for fallback targets and the scripted demo."""


def format_mock_launch_output(window_title: str, handle: int) -> str:
    """Human-readable mock-substrate launch confirmation (legacy format)."""
    return f"Launched new {window_title} window (Mock HWND: {handle})"


class NativeWindowManager:
    """Desktop Window Manager for discovering, positioning, and tiling windows deterministically."""

    def __init__(
        self,
        substrate: Optional[MockWindowManagerSubstrate] = None,
        screen_width: int = 1920,
        screen_height: int = 1080,
    ) -> None:
        if substrate is None and not NativeWindowManager.live_substrate_available():
            self.substrate = MockWindowManagerSubstrate()
        else:
            self.substrate = substrate
        self.screen_width = screen_width
        self.screen_height = screen_height
        self._is_windows = sys.platform == "win32" and self.substrate is None

    # =========================================================================
    # Capability Probes & App Vocabulary Queries
    # =========================================================================
    # Single source of truth for host capability and desktop app vocabulary.
    # App-layer callers (agent, CLI) branch ONLY on these queries — never on
    # sys.platform or a local copy of the vocabulary (CHECK-A leg ii).

    @staticmethod
    def live_substrate_available() -> bool:
        """Capability probe: can this host drive real native windows?"""
        if sys.platform != "win32":
            return False
        try:
            import ctypes
        except ImportError:
            return False
        return hasattr(ctypes, "windll")

    @property
    def supports_live_management(self) -> bool:
        """True when this manager drives real OS windows (no mock substrate)."""
        return self.substrate is None and NativeWindowManager.live_substrate_available()

    def supported_app_terms(self) -> Tuple[str, ...]:
        """Full launch-routing vocabulary for window-management commands."""
        return APP_ROUTING_TERMS

    def resolve_app_launch(self, app_text: str) -> Optional[AppLaunchSpec]:
        """Resolves launch vocabulary text to a spec, or None (denied)."""
        lowered = app_text.lower()
        for spec in APP_LAUNCH_TABLE:
            if any(term in lowered for term in spec.match_terms):
                return spec
        return None

    def launch_allowlist_text(self) -> str:
        """Parenthesized allowlist suffix for launch-denied messages."""
        labels = ["/".join(spec.match_terms) for spec in APP_LAUNCH_TABLE]
        return "(allowlist: " + ", ".join(labels) + ")."

    def resolve_process_filter(self, command_text: str) -> Optional[str]:
        """Resolves tiling process-filter token from command text, if any."""
        lowered = command_text.lower()
        for spec in APP_LAUNCH_TABLE:
            if spec.filter_token is not None and any(
                term in lowered for term in spec.filter_terms
            ):
                return spec.filter_token
        return None

    def resolve_window_target_or_default(self) -> str:
        """Focused handle, else first window handle, else default app key."""
        focused = self.get_focused_window()
        if focused is not None:
            return str(focused.handle)
        windows = self.list_windows()
        if windows:
            return str(windows[0].handle)
        return DEFAULT_APP_KEY

    def seed_mock_windows_if_empty(
        self,
        process_filter: Optional[str] = None,
        count: int = 3,
    ) -> int:
        """In mock mode with no matching windows, seeds demo windows.

        Returns the number of windows added (0 when live or non-empty).
        """
        if self.substrate is None:
            return 0
        if self.list_windows(process_name=process_filter):
            return 0
        for i in range(1, count + 1):
            self.substrate.add_window(f"Notes_{i}.txt - Notepad", process_name="notepad.exe")
        return count

    @staticmethod
    def is_calculator_process(process_name: str) -> bool:
        """Whether a process name denotes a calculator window (legacy rule)."""
        return "calc" in process_name

    @staticmethod
    def is_text_editor_process(process_name: str) -> bool:
        """Whether a process name denotes a text editor window (legacy rule)."""
        return "notepad" in process_name

    # =========================================================================
    # Window Discovery
    # =========================================================================

    def list_windows(
        self,
        process_name: Optional[str] = None,
        title_query: Optional[str] = None,
        visible_only: bool = True,
    ) -> List[WindowInfo]:
        """Lists active top-level windows matching optional process or title filters."""
        if self._is_windows:
            results = self._list_windows_win32()
        elif self.substrate is not None:
            results = [
                WindowInfo(
                    handle=w["handle"],
                    title=w["title"],
                    process_name=w["process_name"],
                    x=w["x"],
                    y=w["y"],
                    width=w["width"],
                    height=w["height"],
                    is_minimized=w.get("is_minimized", False),
                    is_maximized=w.get("is_maximized", False),
                    is_visible=w.get("is_visible", True),
                )
                for w in self.substrate.list_windows()
            ]
        else:
            results = []

        filtered: List[WindowInfo] = []
        for w in results:
            if visible_only and not w.is_visible:
                continue
            if process_name and process_name.lower() not in w.process_name.lower():
                continue
            if title_query and title_query.lower() not in w.title.lower():
                continue
            filtered.append(w)

        return filtered

    def find_windows(self, query: str) -> List[WindowInfo]:
        """Finds windows matching query against title or process name."""
        q = query.strip().lower()
        all_windows = self.list_windows(visible_only=True)
        return [w for w in all_windows if q in w.title.lower() or q in w.process_name.lower()]

    def get_focused_window(self) -> Optional[WindowInfo]:
        """Returns the currently active foreground window."""
        if self._is_windows:
            try:
                import ctypes
                from ctypes import wintypes

                user32 = ctypes.windll.user32
                user32.GetForegroundWindow.argtypes = []
                user32.GetForegroundWindow.restype = wintypes.HWND
                hwnd = user32.GetForegroundWindow()
                if hwnd:
                    for w in self._list_windows_win32():
                        if w.handle == hwnd:
                            return w
            except Exception:
                pass
        elif self.substrate is not None and self.substrate.focused_handle is not None:
            for w in self.list_windows():
                if w.handle == self.substrate.focused_handle:
                    return w
        return None

    # =========================================================================
    # Window Manipulation
    # =========================================================================

    def move_resize_window(
        self,
        target: Union[int, str],
        x: int,
        y: int,
        width: int,
        height: int,
    ) -> bool:
        """Sets the exact position and dimensions of a window."""
        hwnd = self._resolve_handle(target)
        if hwnd is None:
            return False

        if self._is_windows:
            return self._set_window_pos_win32(hwnd, x, y, width, height)
        elif self.substrate is not None:
            return self.substrate.set_bounds(hwnd, x, y, width, height)
        return False

    def focus_window(self, target: Union[int, str]) -> bool:
        """Brings the window to the foreground and focuses it."""
        hwnd = self._resolve_handle(target)
        if hwnd is None:
            return False

        if self._is_windows:
            try:
                import ctypes
                from ctypes import wintypes

                user32 = ctypes.windll.user32
                user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
                user32.ShowWindow.restype = wintypes.BOOL
                user32.SetForegroundWindow.argtypes = [wintypes.HWND]
                user32.SetForegroundWindow.restype = wintypes.BOOL

                # SW_RESTORE = 9
                user32.ShowWindow(hwnd, 9)
                return bool(user32.SetForegroundWindow(hwnd))
            except Exception:
                return False
        elif self.substrate is not None:
            return self.substrate.focus_window(hwnd)
        return False

    def minimize_window(self, target: Union[int, str]) -> bool:
        """Minimizes the window."""
        hwnd = self._resolve_handle(target)
        if hwnd is None:
            return False

        if self._is_windows:
            try:
                import ctypes
                from ctypes import wintypes

                user32 = ctypes.windll.user32
                user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
                user32.ShowWindow.restype = wintypes.BOOL

                # SW_MINIMIZE = 6
                return bool(user32.ShowWindow(hwnd, 6))
            except Exception:
                return False
        elif self.substrate is not None:
            return self.substrate.minimize_window(hwnd)
        return False

    def maximize_window(self, target: Union[int, str]) -> bool:
        """Maximizes the window."""
        hwnd = self._resolve_handle(target)
        if hwnd is None:
            return False

        if self._is_windows:
            try:
                import ctypes
                from ctypes import wintypes

                user32 = ctypes.windll.user32
                user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
                user32.ShowWindow.restype = wintypes.BOOL

                # SW_MAXIMIZE = 3
                return bool(user32.ShowWindow(hwnd, 3))
            except Exception:
                return False
        elif self.substrate is not None:
            return self.substrate.maximize_window(hwnd)
        return False

    def restore_window(self, target: Union[int, str]) -> bool:
        """Restores a minimized or maximized window to normal size."""
        hwnd = self._resolve_handle(target)
        if hwnd is None:
            return False

        if self._is_windows:
            try:
                import ctypes
                from ctypes import wintypes

                user32 = ctypes.windll.user32
                user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
                user32.ShowWindow.restype = wintypes.BOOL

                # SW_RESTORE = 9
                return bool(user32.ShowWindow(hwnd, 9))
            except Exception:
                return False
        elif self.substrate is not None:
            return self.substrate.restore_window(hwnd)
        return False

    def close_window(self, target: Union[int, str]) -> bool:
        """Closes the specified window."""
        hwnd = self._resolve_handle(target)
        if hwnd is None:
            return False

        if self._is_windows:
            try:
                import ctypes
                from ctypes import wintypes

                user32 = ctypes.windll.user32
                user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
                user32.PostMessageW.restype = wintypes.BOOL

                # WM_CLOSE = 0x0010
                user32.PostMessageW(hwnd, 0x0010, 0, 0)
                return True
            except Exception:
                return False
        elif self.substrate is not None:
            return self.substrate.close_window(hwnd)
        return False

    # =========================================================================
    # High-Level Deterministic Tiling
    # =========================================================================

    def tile_windows(
        self,
        layout: str = "grid",
        process_filter: Optional[str] = None,
        title_filter: Optional[str] = None,
        screen_width: Optional[int] = None,
        screen_height: Optional[int] = None,
        margin: int = 10,
    ) -> List[Dict[str, Any]]:
        """Instantly tiles matching windows across the screen without fragile mouse drags.

        Supported layouts:
        - "grid": Computes optimal rows x cols matrix.
        - "horizontal": Side-by-side vertical columns.
        - "vertical": Stacked horizontal rows.
        """
        sw = screen_width or self.screen_width
        sh = screen_height or self.screen_height

        # Discover matching windows
        windows = self.list_windows(process_name=process_filter, title_query=title_filter, visible_only=True)
        if not windows:
            return []

        n = len(windows)
        slots: List[Tuple[int, int, int, int]] = []
        layout_norm = layout.lower().strip()

        if layout_norm in ("horizontal", "columns", "side by side", "col") or (layout_norm == "grid" and n == 2):
            col_width = max(50, (sw - (n + 1) * margin) // n)
            row_height = max(50, sh - 2 * margin)
            for i in range(n):
                x = margin + i * (col_width + margin)
                y = margin
                slots.append((x, y, col_width, row_height))

        elif layout_norm in ("vertical", "rows", "stacked", "row"):
            row_height = max(50, (sh - (n + 1) * margin) // n)
            col_width = max(50, sw - 2 * margin)
            for i in range(n):
                x = margin
                y = margin + i * (row_height + margin)
                slots.append((x, y, col_width, row_height))

        else:  # Grid layout
            cols = max(1, math.ceil(math.sqrt(n)))
            rows = max(1, math.ceil(n / cols))
            col_width = max(50, (sw - (cols + 1) * margin) // cols)
            row_height = max(50, (sh - (rows + 1) * margin) // rows)

            for i in range(n):
                r = i // cols
                c = i % cols
                x = margin + c * (col_width + margin)
                y = margin + r * (row_height + margin)
                slots.append((x, y, col_width, row_height))

        applied: List[Dict[str, Any]] = []
        for w, (x, y, width, height) in zip(windows, slots):
            # Restore window first if minimized
            if w.is_minimized:
                self.restore_window(w.handle)
            self.move_resize_window(w.handle, x, y, width, height)
            applied.append(
                {
                    "handle": w.handle,
                    "title": w.title,
                    "process_name": w.process_name,
                    "bounds": {"x": x, "y": y, "width": width, "height": height},
                }
            )

        return applied

    def launch_application(self, command_or_path: str) -> Optional[subprocess.Popen]:
        """Spawns an application process. In mock substrate mode, registers the window."""
        if self.substrate is not None:
            cmd_lower = command_or_path.lower()
            if "notepad" in cmd_lower:
                title, proc = "Untitled - Notepad", "notepad.exe"
            elif "calc" in cmd_lower:
                title, proc = "Calculator", "calc.exe"
            elif any(b in cmd_lower for b in ("chrome", "browser", "edge")):
                title, proc = "Google Chrome", "chrome.exe"
            elif any(t in cmd_lower for t in ("terminal", "cmd", "powershell")):
                title, proc = "Command Prompt", "cmd.exe"
            else:
                base = os.path.basename(command_or_path).split()[0]
                title, proc = f"{base.capitalize()} Window", f"{base}.exe"
            self.substrate.add_window(title=title, process_name=proc)
            return None

        argv = shlex.split(command_or_path, posix=False)
        if argv and argv[0].lower() == "start":
            # `start` is a cmd.exe shell builtin; launch the target directly.
            argv = argv[1:]
        if not argv:
            raise ValueError(f"Empty launch command: {command_or_path!r}")
        proc = subprocess.Popen(
            argv,
            shell=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        return proc

    # =========================================================================
    # Helpers & Win32 Implementation
    # =========================================================================

    def _resolve_handle(self, target: Union[int, str]) -> Optional[int]:
        if isinstance(target, int):
            return target
        target_str = str(target).strip().lower()
        if target_str.startswith("0x"):
            try:
                return int(target_str, 16)
            except ValueError:
                pass
        match_hwnd = re.search(r"hwnd\s*(\d+|0x[0-9a-f]+)", target_str)
        if match_hwnd:
            val = match_hwnd.group(1)
            try:
                return int(val, 16) if val.startswith("0x") else int(val)
            except ValueError:
                pass
        if target_str.isdigit():
            return int(target_str)
        # Match by title or process
        matches = self.find_windows(target_str)
        if matches:
            return matches[0].handle
        return None

    def _list_windows_win32(self) -> List[WindowInfo]:
        try:
            import ctypes
            from ctypes import wintypes

            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32

            class RECT(ctypes.Structure):
                _fields_ = [
                    ("left", ctypes.c_long),
                    ("top", ctypes.c_long),
                    ("right", ctypes.c_long),
                    ("bottom", ctypes.c_long),
                ]

            # Set explicit 64-bit argtypes and restypes
            WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
            user32.EnumWindows.argtypes = [WNDENUMPROC, wintypes.LPARAM]
            user32.EnumWindows.restype = wintypes.BOOL
            user32.IsWindowVisible.argtypes = [wintypes.HWND]
            user32.IsWindowVisible.restype = wintypes.BOOL
            user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
            user32.GetWindowTextLengthW.restype = ctypes.c_int
            user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
            user32.GetWindowTextW.restype = ctypes.c_int
            user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(RECT)]
            user32.GetWindowRect.restype = wintypes.BOOL
            user32.IsIconic.argtypes = [wintypes.HWND]
            user32.IsIconic.restype = wintypes.BOOL
            user32.IsZoomed.argtypes = [wintypes.HWND]
            user32.IsZoomed.restype = wintypes.BOOL
            user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
            user32.GetWindowThreadProcessId.restype = wintypes.DWORD

            windows: List[WindowInfo] = []

            def enum_proc(hwnd: int, lparam: Any) -> bool:
                if not user32.IsWindowVisible(hwnd):
                    return True
                length = user32.GetWindowTextLengthW(hwnd)
                if length == 0:
                    return True

                buf = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buf, length + 1)
                title = buf.value.strip()
                if not title:
                    return True

                rect = RECT()
                user32.GetWindowRect(hwnd, ctypes.byref(rect))
                w = max(0, rect.right - rect.left)
                h = max(0, rect.bottom - rect.top)

                is_min = bool(user32.IsIconic(hwnd))
                is_max = bool(user32.IsZoomed(hwnd))

                # Retrieve process name
                pid = wintypes.DWORD()
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                proc_name = "unknown"
                try:
                    import psutil

                    proc_name = psutil.Process(pid.value).name()
                except Exception:
                    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
                    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
                    kernel32.OpenProcess.restype = wintypes.HANDLE
                    h_proc = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
                    if h_proc:
                        buf_name = ctypes.create_unicode_buffer(260)
                        size = wintypes.DWORD(260)
                        try:
                            kernel32.QueryFullProcessImageNameW.argtypes = [
                                wintypes.HANDLE,
                                wintypes.DWORD,
                                wintypes.LPWSTR,
                                ctypes.POINTER(wintypes.DWORD),
                            ]
                            kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
                            kernel32.QueryFullProcessImageNameW(h_proc, 0, buf_name, ctypes.byref(size))
                            proc_name = os.path.basename(buf_name.value)
                        finally:
                            kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
                            kernel32.CloseHandle.restype = wintypes.BOOL
                            kernel32.CloseHandle(h_proc)

                windows.append(
                    WindowInfo(
                        handle=int(hwnd),
                        title=title,
                        process_name=proc_name,
                        x=rect.left,
                        y=rect.top,
                        width=w,
                        height=h,
                        is_minimized=is_min,
                        is_maximized=is_max,
                        is_visible=True,
                    )
                )
                return True

            cb = WNDENUMPROC(enum_proc)
            user32.EnumWindows(cb, 0)
            return windows
        except Exception:
            return []

    def _set_window_pos_win32(self, hwnd: int, x: int, y: int, width: int, height: int) -> bool:
        try:
            import ctypes
            from ctypes import wintypes

            user32 = ctypes.windll.user32
            user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
            user32.ShowWindow.restype = wintypes.BOOL
            user32.IsIconic.argtypes = [wintypes.HWND]
            user32.IsIconic.restype = wintypes.BOOL
            user32.SetWindowPos.argtypes = [
                wintypes.HWND,
                wintypes.HWND,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_int,
                wintypes.UINT,
            ]
            user32.SetWindowPos.restype = wintypes.BOOL

            SWP_SHOWWINDOW = 0x0040
            if user32.IsIconic(hwnd):
                user32.ShowWindow(hwnd, 9)  # SW_RESTORE
            ret = user32.SetWindowPos(hwnd, 0, x, y, width, height, SWP_SHOWWINDOW)
            return bool(ret)
        except Exception:
            return False
