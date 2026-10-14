"""anima.reflex: alias of the independently installed ``reflex`` distribution.

The real code lives in ``components/reflex`` and is installed with::

    pip install -e components/reflex

Native import (``import reflex``) remains primary; this module is the same
object, provided as a convenience alias. Note: the ``reflex`` import name
collides with the unrelated Reflex web framework on PyPI — do not install
both in one environment.
"""

from __future__ import annotations

import sys
from importlib import import_module

try:
    _mod = import_module("reflex")
except ImportError as exc:
    raise ImportError(
        "anima.reflex needs the 'reflex' distribution, which is not "
        "installed. From the repo root run: "
        "pip install -e components/reflex (see README.md)"
    ) from exc

sys.modules[__name__] = _mod
del _mod
