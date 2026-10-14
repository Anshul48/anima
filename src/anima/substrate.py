"""anima.substrate: alias of the independently installed ``anima_substrate`` distribution.

The real code lives in ``components/substrate`` and is installed with::

    pip install -e components/substrate

Native import (``import anima_substrate``) remains primary; this module is
the same object, provided as a convenience alias.
"""

from __future__ import annotations

import sys
from importlib import import_module

try:
    _mod = import_module("anima_substrate")
except ImportError as exc:
    raise ImportError(
        "anima.substrate needs the 'anima_substrate' distribution, which is "
        "not installed. From the repo root run: "
        "pip install -e components/substrate (see README.md)"
    ) from exc

sys.modules[__name__] = _mod
del _mod
