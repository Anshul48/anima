"""Reflex Browser Session Manager: Profile isolation, download interception, and session lifecycle."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
import os
from pathlib import Path
import shutil
import tempfile
import time
from typing import Any, AsyncIterator, Callable, Dict, List, Optional, Tuple, Union
import uuid

from reflex.integrations.fakes.fake_browser import FakeBrowserPage


@dataclass
class BrowserSessionConfig:
    """Configuration for an isolated browser session context."""
    user_data_dir: Optional[str] = None
    downloads_dir: Optional[str] = None
    viewport_size: Tuple[int, int] = (1920, 1080)
    headless: bool = True
    auto_dismiss_dialogs: bool = True
    dialog_action: str = "accept"  # "accept" or "dismiss"
    clean_on_exit: bool = True
    extra_options: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_data_dir": self.user_data_dir,
            "downloads_dir": self.downloads_dir,
            "viewport_size": list(self.viewport_size),
            "headless": self.headless,
            "auto_dismiss_dialogs": self.auto_dismiss_dialogs,
            "dialog_action": self.dialog_action,
            "clean_on_exit": self.clean_on_exit,
            "extra_options": dict(self.extra_options),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> BrowserSessionConfig:
        raw_vp = data.get("viewport_size", (1920, 1080))
        viewport_size = (int(raw_vp[0]), int(raw_vp[1]))
        return cls(
            user_data_dir=data.get("user_data_dir"),
            downloads_dir=data.get("downloads_dir"),
            viewport_size=viewport_size,
            headless=bool(data.get("headless", True)),
            auto_dismiss_dialogs=bool(data.get("auto_dismiss_dialogs", True)),
            dialog_action=str(data.get("dialog_action", "accept")),
            clean_on_exit=bool(data.get("clean_on_exit", True)),
            extra_options=dict(data.get("extra_options", {})),
        )


@dataclass
class BrowserSession:
    """Active managed browser execution context."""
    session_id: str
    user_data_dir: str
    downloads_dir: str
    page: Optional[Any] = None
    cdp_session: Optional[Any] = None
    is_temp_user_data_dir: bool = False
    is_temp_downloads_dir: bool = False
    config: BrowserSessionConfig = field(default_factory=BrowserSessionConfig)
    dialog_events: List[Dict[str, Any]] = field(default_factory=list)
    download_events: List[Dict[str, Any]] = field(default_factory=list)
    is_closed: bool = False

    def record_dialog_event(self, dialog_type: str, message: str, prompt_text: str = "", handled: bool = True) -> None:
        """Records a JavaScript dialog (alert/confirm/prompt) interception."""
        self.dialog_events.append({
            "type": dialog_type,
            "message": message,
            "prompt_text": prompt_text,
            "handled": handled,
            "timestamp": time.time(),
        })

    def record_download_event(self, url: str, suggested_filename: str, file_path: str) -> None:
        """Records a completed or in-progress browser download."""
        self.download_events.append({
            "url": url,
            "suggested_filename": suggested_filename,
            "file_path": file_path,
            "timestamp": time.time(),
        })

    async def close(self) -> None:
        """Closes page/CDP connections and cleans up temporary isolation directories."""
        if self.is_closed:
            return

        self.is_closed = True

        # 1. Close CDP Session
        if self.cdp_session is not None:
            try:
                if hasattr(self.cdp_session, "detach"):
                    await self.cdp_session.detach()
                elif hasattr(self.cdp_session, "close"):
                    res = self.cdp_session.close()
                    if asyncio.iscoroutine(res):
                        await res
            except Exception:
                pass
            self.cdp_session = None

        # 2. Close Page / Browser Context
        if self.page is not None:
            try:
                if hasattr(self.page, "close"):
                    res = self.page.close()
                    if asyncio.iscoroutine(res):
                        await res
            except Exception:
                pass
            self.page = None

        # 3. Clean temporary directories if clean_on_exit is True
        if self.config.clean_on_exit:
            if self.is_temp_user_data_dir and os.path.exists(self.user_data_dir):
                shutil.rmtree(self.user_data_dir, ignore_errors=True)
            if self.is_temp_downloads_dir and os.path.exists(self.downloads_dir):
                shutil.rmtree(self.downloads_dir, ignore_errors=True)


class BrowserSessionManager:
    """Manages profile isolation, downloads interception, and lifecycle of browser sessions."""

    def __init__(self, default_config: Optional[BrowserSessionConfig] = None) -> None:
        self.default_config = default_config or BrowserSessionConfig()
        self._active_sessions: Dict[str, BrowserSession] = {}
        self._lock = asyncio.Lock()

    @property
    def active_sessions(self) -> Dict[str, BrowserSession]:
        return dict(self._active_sessions)

    async def create_session(
        self,
        session_id: Optional[str] = None,
        config: Optional[BrowserSessionConfig] = None,
        page: Optional[Any] = None,
        cdp_session: Optional[Any] = None,
    ) -> BrowserSession:
        """Creates and configures an isolated browser session."""
        cfg = config or self.default_config
        sid = session_id or f"sess_{uuid.uuid4().hex[:12]}"

        # 1. User Data Directory Setup
        is_temp_profile = False
        if cfg.user_data_dir:
            profile_dir = cfg.user_data_dir
            Path(profile_dir).mkdir(parents=True, exist_ok=True)
        else:
            profile_dir = tempfile.mkdtemp(prefix=f"reflex_profile_{sid}_")
            is_temp_profile = True

        # 2. Downloads Directory Setup
        is_temp_dl = False
        if cfg.downloads_dir:
            dl_dir = cfg.downloads_dir
            Path(dl_dir).mkdir(parents=True, exist_ok=True)
        else:
            dl_dir = tempfile.mkdtemp(prefix=f"reflex_downloads_{sid}_")
            is_temp_dl = True

        # 3. Instantiate or bind page
        active_page = page if page is not None else FakeBrowserPage(
            viewport_width=cfg.viewport_size[0],
            viewport_height=cfg.viewport_size[1],
        )

        # 4. Bind CDP session if available
        active_cdp = cdp_session
        if active_cdp is None and hasattr(active_page, "get_cdp_session"):
            try:
                active_cdp = active_page.get_cdp_session()
            except Exception:
                active_cdp = None

        session = BrowserSession(
            session_id=sid,
            user_data_dir=profile_dir,
            downloads_dir=dl_dir,
            page=active_page,
            cdp_session=active_cdp,
            is_temp_user_data_dir=is_temp_profile,
            is_temp_downloads_dir=is_temp_dl,
            config=cfg,
        )

        # 5. Hook Dialog & CDP handlers
        self._setup_dialog_and_download_hooks(session)

        async with self._lock:
            self._active_sessions[sid] = session

        return session

    def _setup_dialog_and_download_hooks(self, session: BrowserSession) -> None:
        """Registers listeners for JavaScript dialogs and download events."""
        page = session.page
        cfg = session.config

        # Playwright-style dialog listener
        if hasattr(page, "on"):
            try:
                def dialog_handler(dialog: Any) -> None:
                    msg = getattr(dialog, "message", "")
                    dtype = getattr(dialog, "type", "alert")
                    default_prompt = getattr(dialog, "default_value", "")
                    session.record_dialog_event(dtype, msg, default_prompt, handled=cfg.auto_dismiss_dialogs)
                    if cfg.auto_dismiss_dialogs:
                        if hasattr(dialog, "accept") and cfg.dialog_action == "accept":
                            asyncio.create_task(dialog.accept())
                        elif hasattr(dialog, "dismiss"):
                            asyncio.create_task(dialog.dismiss())

                page.on("dialog", dialog_handler)
            except Exception:
                pass

        # CDP session handlers
        if session.cdp_session is not None and hasattr(session.cdp_session, "handlers"):
            async def handle_js_dialog(params: Dict[str, Any]) -> Dict[str, Any]:
                msg = params.get("message", "")
                dtype = params.get("type", "alert")
                default_prompt = params.get("defaultPrompt", "")
                session.record_dialog_event(dtype, msg, default_prompt, handled=cfg.auto_dismiss_dialogs)
                return {"status": "ok"}

            session.cdp_session.handlers["Page.javascriptDialogOpening"] = handle_js_dialog

    async def get_session(self, session_id: str) -> Optional[BrowserSession]:
        """Retrieves an active session by ID."""
        async with self._lock:
            return self._active_sessions.get(session_id)

    async def close_session(self, session_or_id: Union[BrowserSession, str]) -> None:
        """Closes and unregisters a browser session."""
        session_id = session_or_id.session_id if isinstance(session_or_id, BrowserSession) else str(session_or_id)
        async with self._lock:
            session = self._active_sessions.pop(session_id, None)

        if session is not None:
            await session.close()
        elif isinstance(session_or_id, BrowserSession):
            await session_or_id.close()

    async def cleanup_all(self) -> None:
        """Closes all active sessions and performs clean disk teardown."""
        async with self._lock:
            sessions = list(self._active_sessions.values())
            self._active_sessions.clear()

        for session in sessions:
            try:
                await session.close()
            except Exception:
                pass

    @asynccontextmanager
    async def session_context(
        self,
        session_id: Optional[str] = None,
        config: Optional[BrowserSessionConfig] = None,
        page: Optional[Any] = None,
    ) -> AsyncIterator[BrowserSession]:
        """Async context manager scoping a single session lifecycle."""
        session = await self.create_session(session_id=session_id, config=config, page=page)
        try:
            yield session
        finally:
            await self.close_session(session)

    async def __aenter__(self) -> BrowserSessionManager:
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.cleanup_all()
