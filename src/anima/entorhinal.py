"""anima.entorhinal: alias of the independently installed ``entorhinal`` distribution.

The real code lives in ``components/entorhinal`` and is installed with::

    pip install -e components/entorhinal

Native import (``import entorhinal``) remains primary; this module is the
same object, provided as a convenience alias.
"""

from __future__ import annotations

import sys
from importlib import import_module

try:
    _mod = import_module("entorhinal")
except ImportError as exc:
    raise ImportError(
        "anima.entorhinal needs the 'entorhinal' distribution, which is not "
        "installed. From the repo root run: "
        "pip install -e components/entorhinal (see README.md)"
    ) from exc

sys.modules[__name__] = _mod
del _mod
