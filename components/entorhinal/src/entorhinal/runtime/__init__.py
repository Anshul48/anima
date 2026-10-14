"""Runtime package: one explicit configuration/factory path for serve and CLI."""

from entorhinal.runtime.config import RuntimeConfig, SourceSpec
from entorhinal.runtime.factory import Runtime, build_runtime, close_runtime
from entorhinal.runtime.sources import (
    SourceLifecycle,
    create_adapter,
    register_adapter,
    registered_adapters,
)

# The dev-task inbox tailer is the first real producer; registering on package
# import keeps serve/CLI/factory on the single configuration path.
from entorhinal.sources.dev_task import register_dev_task_adapter as _register_dev_task

_register_dev_task()
del _register_dev_task

# Activity producers (activity-build/INTERFACES.md §8.1): opt-in inbox tailer
# for ActivityEvent JSONL. Guarded during parallel development so in-flight
# activity edits can never break the core runtime import; the registration
# is purely additive (no behavior change unless a spec selects it).
try:
    from entorhinal.activity.producers.inbox import (
        register_activity_adapters as _register_activity,
    )

    _register_activity()
    del _register_activity
except Exception as _activity_import_error:  # pragma: no cover - parallel-dev guard
    import logging as _logging

    _logging.getLogger(__name__).warning(
        "Activity adapters unavailable; continuing without them: %s",
        _activity_import_error,
    )

__all__ = [
    "Runtime",
    "RuntimeConfig",
    "SourceLifecycle",
    "SourceSpec",
    "build_runtime",
    "close_runtime",
    "create_adapter",
    "register_adapter",
    "registered_adapters",
]
