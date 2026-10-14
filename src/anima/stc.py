"""anima.stc: alias of the independently installed ``stc`` distribution.

The real code lives in ``components/stc`` and is installed with::

    pip install -e components/stc

Native import (``import stc``) remains primary; this module is the same
object, provided as a convenience alias.
"""

from __future__ import annotations

import sys
from importlib import import_module

try:
    _mod = import_module("stc")
except ImportError as exc:
    raise ImportError(
        "anima.stc needs the 'stc' distribution, which is not installed. "
        "From the repo root run: pip install -e components/stc (see README.md)"
    ) from exc

sys.modules[__name__] = _mod
del _mod
