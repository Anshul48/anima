"""Injectable-executor seam helpers for the SST search controller.

The controller's verification path resolves its executor through these
helpers: an explicitly bound executor wins, otherwise the controller's own
``executor`` slot (defaulting to ``custody_manager``) is used.
``bind_executor`` validates :class:`ExecutorProtocol` conformance up front
so misconfigured executors fail fast instead of mid-search.

Native constructor injection (``SSTSearchController(..., executor=...)``)
lives in ``sst/search/controller.py``; post-construction binding via
:func:`bind_executor` sets both the ``executor`` and ``custody_manager``
slots for backward compatibility.
"""

from __future__ import annotations

from typing import Any

from sst.core.errors import SSTError
from sst.protocols.executor import ExecutorProtocol


class ExecutorUnavailableError(SSTError):
    """Raised when no executor can be resolved for a controller."""

    pass


def resolve_executor(controller: Any, override: ExecutorProtocol | None = None) -> ExecutorProtocol:
    """Returns the executor a controller should use for candidate verification.

    Precedence: explicit ``override`` first, then a natively injected
    ``controller.executor`` (once B1 lands constructor injection), then the
    default ``controller.custody_manager`` slot.
    """
    if override is not None:
        return override
    native: ExecutorProtocol | None = getattr(controller, "executor", None)
    if native is not None:
        return native
    custody: ExecutorProtocol | None = getattr(controller, "custody_manager", None)
    if custody is not None:
        return custody
    raise ExecutorUnavailableError("No executor available: controller has neither 'executor' nor 'custody_manager'.")


def bind_executor(controller: Any, executor: ExecutorProtocol) -> ExecutorProtocol:
    """Binds ``executor`` to ``controller`` after validating protocol conformance.

    Sets the controller's ``custody_manager`` slot (the seam the current
    verification path reads) and mirrors it to ``executor`` for forward
    compatibility with native constructor injection.
    """
    if not isinstance(executor, ExecutorProtocol):
        raise TypeError(
            "Executor must satisfy ExecutorProtocol (apply_proposal + "
            f"verify_candidate_proposal); got {type(executor).__name__}."
        )
    controller.custody_manager = executor
    try:
        controller.executor = executor
    except AttributeError:
        pass
    return executor
