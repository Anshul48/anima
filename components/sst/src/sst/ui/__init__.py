"""SST task-to-result browser UI (real backend, stdlib HTTP server)."""

from __future__ import annotations

from typing import Any

__all__ = ["SSTUIServer", "create_server", "main"]


def __getattr__(name: str) -> Any:
    if name in __all__:
        from sst.ui import app

        return getattr(app, name)
    raise AttributeError(f"module 'sst.ui' has no attribute {name!r}")
