"""anima.sst: alias of the independently installed ``sst`` distribution.

The real code lives in ``components/sst`` and is installed with::

    pip install -e components/sst

Native import (``import sst``) remains primary; this module is the same
object, provided as a convenience alias.
"""

from __future__ import annotations

import sys
from importlib import import_module

try:
    _mod = import_module("sst")
except ImportError as exc:
    raise ImportError(
        "anima.sst needs the 'sst' distribution, which is not installed. "
        "From the repo root run: pip install -e components/sst (see README.md)"
    ) from exc

sys.modules[__name__] = _mod
del _mod
