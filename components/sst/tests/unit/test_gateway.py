"""Unit tests for ModelGateway OpenAI-compatible response mapping."""

from __future__ import annotations

import io
import json
from typing import Any

from sst.gateway.contracts import (
    GatewayRequest,
    ModelCatalog,
    ModelCatalogEntry,
    ProviderKind,
    ProviderProfile,
)
from sst.gateway.gateway import ModelGateway


class _FakeHTTPResponse(io.BytesIO):
    def __enter__(self) -> _FakeHTTPResponse:
        return self

    def __exit__(self, *args: Any) -> None:
        return None


def _sail_like_gateway() -> ModelGateway:
    gateway = ModelGateway()
    gateway.register_profile(
        ProviderProfile(
            name="sail",
            kind=ProviderKind.OPENAI_COMPATIBLE,
            api_base="https://api.example.com/v1",
            selected_model="reasoning-model",
            catalog=ModelCatalog(models=[ModelCatalogEntry(id="reasoning-model", display_label="R")]),
        )
    )
    gateway.set_route("diverge", "sail", "reasoning-model")
    return gateway


def _chat_payload(content: Any) -> bytes:
    return json.dumps(
        {
            "choices": [{"message": {"content": content, "reasoning_content": "..."}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
        }
    ).encode("utf-8")


def test_null_content_maps_to_empty_string(monkeypatch: Any) -> None:
    """Reasoning providers may return content:null; it must not become literal 'None'."""
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda *a, **k: _FakeHTTPResponse(_chat_payload(None)),
    )
    resp = _sail_like_gateway().invoke(GatewayRequest(role="diverge", messages=[{"role": "user", "content": "hi"}]))
    assert resp.content == ""
    assert resp.total_tokens == 30


def test_string_content_passes_through(monkeypatch: Any) -> None:
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda *a, **k: _FakeHTTPResponse(_chat_payload("hello")),
    )
    resp = _sail_like_gateway().invoke(GatewayRequest(role="diverge", messages=[{"role": "user", "content": "hi"}]))
    assert resp.content == "hello"


def test_unpriced_profile_cost_unknown(monkeypatch: Any) -> None:
    """Without USD rates, cost_usd must be flagged unknown, never a silent zero."""
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda *a, **k: _FakeHTTPResponse(_chat_payload("hi")),
    )
    resp = _sail_like_gateway().invoke(GatewayRequest(role="diverge", messages=[{"role": "user", "content": "hi"}]))
    assert resp.cost_usd == 0.0
    assert resp.cost_known is False


def test_priced_profile_computes_cost(monkeypatch: Any) -> None:
    gateway = _sail_like_gateway()
    profile = gateway.get_profile("sail")
    assert profile is not None
    profile.input_usd_per_1k_tokens = 1.0
    profile.output_usd_per_1k_tokens = 4.0
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda *a, **k: _FakeHTTPResponse(_chat_payload("hi")),
    )
    resp = gateway.invoke(GatewayRequest(role="diverge", messages=[{"role": "user", "content": "hi"}]))
    assert resp.cost_known is True
    assert resp.cost_usd == (10 / 1000.0) * 1.0 + (20 / 1000.0) * 4.0


def test_half_priced_profile_stays_unknown(monkeypatch: Any) -> None:
    gateway = _sail_like_gateway()
    profile = gateway.get_profile("sail")
    assert profile is not None
    profile.input_usd_per_1k_tokens = 1.0
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda *a, **k: _FakeHTTPResponse(_chat_payload("hi")),
    )
    resp = gateway.invoke(GatewayRequest(role="diverge", messages=[{"role": "user", "content": "hi"}]))
    assert resp.cost_known is False
