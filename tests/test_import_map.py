"""Root smoke tests for the anima alias map (stdlib-only, no components needed)."""

import importlib
import sys

import pytest

import anima

ALIASES = {
    "substrate": "anima_substrate",
    "sst": "sst",
    "stc": "stc",
    "entorhinal": "entorhinal",
    "reflex": "reflex",
}


def test_version_present():
    assert anima.__version__ == "0.1.0"


def test_components_reports_all_aliases():
    status = anima.components()
    assert set(status) == set(ALIASES)
    assert all(isinstance(v, bool) for v in status.values())


def test_missing_component_raises_helpful_import_error(monkeypatch):
    # Simulate "reflex distribution not installed" without touching the env.
    import importlib.util

    real_find_spec = importlib.util.find_spec
    real_import_module = importlib.import_module

    def fake_find_spec(name, *args, **kwargs):
        if name == "reflex":
            return None
        return real_find_spec(name, *args, **kwargs)

    def fake_import_module(name, *args, **kwargs):
        if name == "reflex":
            raise ImportError("No module named 'reflex'")
        return real_import_module(name, *args, **kwargs)

    monkeypatch.setattr(importlib.util, "find_spec", fake_find_spec)
    monkeypatch.setattr(importlib, "import_module", fake_import_module)
    monkeypatch.delitem(sys.modules, "anima.reflex", raising=False)
    with pytest.raises(ImportError, match="components/reflex"):
        importlib.import_module("anima.reflex")


@pytest.mark.parametrize("alias,module", sorted(ALIASES.items()))
def test_alias_is_component_module_when_installed(alias, module):
    component = pytest.importorskip(module)
    sys.modules.pop(f"anima.{alias}", None)
    assert importlib.import_module(f"anima.{alias}") is component
