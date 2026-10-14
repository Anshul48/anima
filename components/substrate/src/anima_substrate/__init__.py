# Copyright 2026 Anshul48
# SPDX-License-Identifier: Apache-2.0
"""anima-substrate: maintained substrate package (stdlib-only, offline).

Host mechanisms live in :mod:`anima_substrate.host`, participant
families in :mod:`anima_substrate.participants`, demos in
:mod:`anima_substrate.demos`. All state goes to caller-selected
directories; nothing is written outside them.
"""

from anima_substrate.host import api as api
from anima_substrate.host.minihost import ContractViolation as ContractViolation
from anima_substrate.host.minihost import MiniHost as MiniHost
from anima_substrate.participants import get_family as get_family
from anima_substrate.participants import list_families as list_families
from anima_substrate.participants import registered as registered

# Family registration (import = register; each family module guards
# against double registration). After host imports: family modules
# bind the public host surface only. noqa: side-effect imports.
from anima_substrate.participants.relcheck import v1 as _relcheck_v1  # noqa: F401
from anima_substrate.participants.relcheck import v2 as _relcheck_v2  # noqa: F401
from anima_substrate.participants.sched import family as _sched_family  # noqa: F401
from anima_substrate.participants.sst import SstFamily as _SstFamily  # noqa: F401

__version__ = "0.1.1"

__all__ = [
    "ContractViolation",
    "MiniHost",
    "__version__",
    "api",
    "get_family",
    "list_families",
    "registered",
]
