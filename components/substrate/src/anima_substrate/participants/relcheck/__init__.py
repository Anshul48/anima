# Copyright 2026 Anshul48
# SPDX-License-Identifier: Apache-2.0
"""relcheck participant family: file-backed release-identity checks.

v1 verifies identity pins (manifest_version 1); v2 adds compat
rules (manifest_version 1 or 2) and is the upgrade target for v1
worlds. Both run real file hashing over caller trees — no toy
tasks, no fixtures-as-evidence.
"""

from anima_substrate.participants.relcheck import checker as checker
from anima_substrate.participants.relcheck import runner as runner
from anima_substrate.participants.relcheck import v1 as v1
from anima_substrate.participants.relcheck import v2 as v2

__all__ = ["checker", "runner", "v1", "v2"]
