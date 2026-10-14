"""Terminal PTY Source Adapter for Permitted CLI Ingestion.

Captures loss-free command executions, exit codes, and sanitized output without terminal hangs.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import Any, Dict, Optional, Tuple

from entorhinal.schemas.models import RawSignalEvent, SourceType, generate_uuidv7
from entorhinal.sources.base import BaseSourceAdapter

logger = logging.getLogger(__name__)

# Regex pattern to strip terminal ANSI escape codes from captured output
REGEX_ANSI_ESCAPE: re.Pattern[str] = re.compile(
    r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])"
)


def clean_terminal_output(raw_output: str) -> str:
    """Strip cursor movement and ANSI color escape sequences while preserving text."""
    if not raw_output:
        return ""
    # Strip ANSI sequences
    clean = REGEX_ANSI_ESCAPE.sub("", raw_output)
    # Normalize carriage returns
    clean = clean.replace("\r\n", "\n").replace("\r", "\n")
    return clean.strip()


class TerminalPTYSourceAdapter(BaseSourceAdapter):
    """Permitted capture adapter for pseudo-terminal (PTY/ConPTY) command execution."""

    def __init__(
        self,
        adapter_id: str = "terminal.pty.local",
        max_buffer_size: int = 5000,
        default_timeout_seconds: float = 30.0,
    ) -> None:
        super().__init__(max_buffer_size=max_buffer_size)
        self._adapter_id = adapter_id
        self._default_timeout_seconds = default_timeout_seconds

    @property
    def adapter_id(self) -> str:
        return self._adapter_id

    @property
    def source_type(self) -> SourceType:
        return SourceType.TERMINAL_PTY

    async def capture_command(
        self,
        command: str,
        output: str,
        exit_code: int = 0,
        cwd: Optional[str] = None,
        duration_ms: Optional[float] = None,
        app_identifier: str = "Terminal",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[RawSignalEvent]:
        """Capture a completed CLI command execution and sanitized output."""
        if not self._is_running:
            return None

        clean_out = clean_terminal_output(output)
        meta = dict(metadata or {})
        if cwd is not None:
            meta["cwd"] = cwd
        if duration_ms is not None:
            meta["duration_ms"] = duration_ms

        event = RawSignalEvent(
            signal_id=generate_uuidv7(),
            source_type=self.source_type,
            adapter_id=self.adapter_id,
            app_identifier=app_identifier,
            window_title=f"Terminal - {command[:30]}",
            target_uri=cwd,
            raw_payload={
                "event_type": "command_execution",
                "command": command.strip(),
                "exit_code": exit_code,
                "output": clean_out,
                "cwd": cwd,
            },
            metadata=meta,
        )

        await self.emit_signal(event)
        return event

