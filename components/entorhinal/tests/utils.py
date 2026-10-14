import asyncio
import time
from typing import Optional, Tuple
from entorhinal.sources.terminal_pty import TerminalPTYSourceAdapter
from entorhinal.schemas.models import RawSignalEvent

async def execute_monitored_command(
    adapter: TerminalPTYSourceAdapter,
    command: str,
    cwd: Optional[str] = None,
    timeout_seconds: Optional[float] = None,
) -> Tuple[int, str, Optional[RawSignalEvent]]:
    """Safely execute a shell command asynchronously with timeout protection against hangs."""
    timeout = timeout_seconds if timeout_seconds is not None else getattr(adapter, '_default_timeout_seconds', 30.0)
    start_time = time.perf_counter()

    try:
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=cwd,
        )

        try:
            stdout_data, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            exit_code = proc.returncode if proc.returncode is not None else 0
            output_str = stdout_data.decode("utf-8", errors="replace")
        except asyncio.TimeoutError:
            try:
                proc.kill()
                await proc.wait()
            except Exception:
                pass
            exit_code = -1
            output_str = f"[TIMEOUT] Command exceeded timeout of {timeout}s and was terminated."
    except Exception as e:
        exit_code = -2
        output_str = f"[EXECUTION_ERROR] {str(e)}"

    duration_ms = (time.perf_counter() - start_time) * 1000.0

    signal = await adapter.capture_command(
        command=command,
        output=output_str,
        exit_code=exit_code,
        cwd=cwd,
        duration_ms=duration_ms,
    )

    return exit_code, output_str, signal
