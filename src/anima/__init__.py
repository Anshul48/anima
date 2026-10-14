"""ANIMA mono-repo namespace.

The substance of this repository is the runnable packaged components in
``components/`` (each installed and used under its own distribution name).
This package only provides convenience alias modules so existing code can
also write::

    import anima.substrate  # the anima_substrate distribution
    import anima.sst        # the sst distribution
    import anima.stc        # the stc distribution
    import anima.entorhinal  # the entorhinal distribution
    import anima.reflex     # the reflex distribution

Each ``anima.<component>`` module IS the component module (same object);
no code is copied or wrapped here. Native imports (``import sst.cli``)
remain the primary form — use them for deep submodule imports.
"""

from __future__ import annotations

import importlib.util

__version__ = "0.1.0"

_COMPONENTS: dict[str, tuple[str, str]] = {
    # alias -> (distribution import name, component directory)
    "substrate": ("anima_substrate", "components/substrate"),
    "sst": ("sst", "components/sst"),
    "stc": ("stc", "components/stc"),
    "entorhinal": ("entorhinal", "components/entorhinal"),
    "reflex": ("reflex", "components/reflex"),
}

__all__ = ["__version__", "components"]


def components() -> dict[str, bool]:
    """Map each ``anima.<alias>`` to whether its distribution is importable."""
    return {
        alias: importlib.util.find_spec(module_name) is not None
        for alias, (module_name, _component_dir) in sorted(_COMPONENTS.items())
    }
