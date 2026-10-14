import asyncio
import json
import logging
import struct
import sys
import ctypes
from typing import Optional, Callable, Awaitable
from pydantic import ValidationError

from entorhinal.schemas.vnext import (
    ContextRequestVNext, ContextResultVNext, ContextSnapshotVNext, 
    ContextResultStatus, ContextPurpose
)

logger = logging.getLogger(__name__)

PIPE_NAME = r'\\.\pipe\entorhinal_vnext'
MAX_REQUEST_SIZE = 4096
MAX_RESPONSE_SIZE = 256 * 1024

class NamedPipeServerProtocol(asyncio.Protocol):
    def __init__(self, handler: Callable[[ContextRequestVNext, int], Awaitable[ContextResultVNext]]):
        self.handler = handler
        self.transport = None
        self.buffer = bytearray()
        self.msg_size = None
        self.client_pid = None

    def connection_made(self, transport):
        self.transport = transport
        # On Windows, try to get the client PID
        try:
            handle = transport._get_extra_info('pipe_handle')
            if handle is not None:
                pid = ctypes.c_ulong()
                # GetNamedPipeClientProcessId(handle, &pid)
                res = ctypes.windll.kernel32.GetNamedPipeClientProcessId(handle, ctypes.byref(pid))
                if res:
                    self.client_pid = pid.value
        except Exception as e:
            logger.warning(f"Could not get client PID: {e}")

    def data_received(self, data: bytes):
        self.buffer.extend(data)
        
        if self.msg_size is None and len(self.buffer) >= 4:
            self.msg_size = struct.unpack('!I', self.buffer[:4])[0]
            self.buffer = self.buffer[4:]
            
        if self.msg_size is not None and self.msg_size > MAX_REQUEST_SIZE:
            # Over-sized request
            asyncio.create_task(self.send_error(ContextResultStatus.OVERSIZE, "request_too_large"))
            return

        if self.msg_size is not None and len(self.buffer) >= self.msg_size:
            msg_data = self.buffer[:self.msg_size]
            self.buffer = self.buffer[self.msg_size:]
            self.msg_size = None
            asyncio.create_task(self.process_message(msg_data))

    async def process_message(self, msg_data: bytes):
        try:
            payload = json.loads(msg_data.decode('utf-8'))
            request = ContextRequestVNext(**payload)
            result = await self.handler(request, self.client_pid)
            await self.send_result(result)
        except (json.JSONDecodeError, ValidationError) as e:
            await self.send_error(ContextResultStatus.MALFORMED, "validation_error")
        except Exception as e:
            logger.error(f"Handler error: {e}")
            await self.send_error(ContextResultStatus.UNAVAILABLE, "internal_error")

    async def send_error(self, status: ContextResultStatus, reason: str):
        result = ContextResultVNext(status=status, redacted_diagnostics={"reason": reason})
        await self.send_result(result)

    async def send_result(self, result: ContextResultVNext):
        try:
            resp_data = result.model_dump_json(exclude_none=True).encode('utf-8')
            if len(resp_data) > MAX_RESPONSE_SIZE:
                result = ContextResultVNext(status=ContextResultStatus.OVERSIZE, redacted_diagnostics={"reason": "response_too_large"})
                resp_data = result.model_dump_json(exclude_none=True).encode('utf-8')
                
            self.transport.write(struct.pack('!I', len(resp_data)))
            self.transport.write(resp_data)
        except Exception as e:
            logger.error(f"Error sending result: {e}")
        finally:
            if self.transport:
                self.transport.close()


class VNextProviderServer:
    def __init__(self, handler: Callable[[ContextRequestVNext, int], Awaitable[ContextResultVNext]]):
        self.handler = handler
        self.server = None

    async def start(self):
        loop = asyncio.get_running_loop()
        if sys.platform == 'win32' and hasattr(loop, 'start_serving_pipe'):
            # It requires proactor event loop
            try:
                self.server = await loop.start_serving_pipe(
                    lambda: NamedPipeServerProtocol(self.handler),
                    PIPE_NAME
                )
                logger.info(f"Started vNext Named Pipe server at {PIPE_NAME}")
            except Exception as e:
                logger.error(f"Failed to start named pipe server: {e}")
                raise
        else:
            raise NotImplementedError("vNext server requires Windows Named Pipes with ProactorEventLoop")

    async def stop(self):
        if self.server:
            self.server.close()
            await self.server.wait_closed()
