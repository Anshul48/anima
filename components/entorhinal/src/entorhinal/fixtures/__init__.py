"""Entorhinal Fixtures Package.

Exports the golden synthetic test corpus and helper lookup methods.
"""

from entorhinal.fixtures.golden import (
    GOLDEN_FIXTURES,
    get_fixture_by_id,
    get_fixtures_by_category,
    get_golden_fixtures,
    validate_all_fixtures,
)

__all__ = [
    "GOLDEN_FIXTURES",
    "get_fixture_by_id",
    "get_fixtures_by_category",
    "get_golden_fixtures",
    "validate_all_fixtures",
]
