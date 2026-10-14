"""Test Suite: Local Holo 3.1 Ollama Provider and LLM Client Fallback."""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional
import unittest

from reflex.cognition.system2.providers import (
    DeterministicRulePlanner,
    HoloOllamaProvider,
    MockLLMClient,
    OllamaLLMClient,
)
from reflex.schemas.actions import ActionType


class FakeHttpResponse:
    """Mock HTTP response matching httpx response interface."""

    def __init__(self, status_code: int = 200, json_data: Optional[Dict[str, Any]] = None, text: str = "") -> None:
        self.status_code = status_code
        self._json_data = json_data or {}
        self.text = text or str(json_data)

    def json(self) -> Dict[str, Any]:
        return self._json_data


class FakeAsyncHttpClient:
    """Mock HTTP client simulating Ollama REST endpoints."""

    def __init__(self) -> None:
        self.calls: List[Dict[str, Any]] = []
        self.get_responses: Dict[str, FakeHttpResponse] = {
            "/api/version": FakeHttpResponse(200, {"version": "0.1.30"}),
            "/api/tags": FakeHttpResponse(200, {"models": [{"name": "holo3.1:9b"}, {"name": "llama3:8b"}]}),
        }
        self.post_response: Optional[FakeHttpResponse] = FakeHttpResponse(
            200,
            {"response": '{"thought": "test plan", "action_type": "click", "target_label": "Submit"}'},
        )
        self.fail_post_count: int = 0
        self.post_exception: Optional[Exception] = None

    async def get(self, url: str) -> FakeHttpResponse:
        self.calls.append({"method": "GET", "url": url})
        for path, resp in self.get_responses.items():
            if url.endswith(path):
                return resp
        return FakeHttpResponse(404, {"error": "not found"})

    async def post(self, url: str, json: Optional[Dict[str, Any]] = None) -> FakeHttpResponse:
        self.calls.append({"method": "POST", "url": url, "json": json})
        if self.post_exception is not None:
            raise self.post_exception

        if self.fail_post_count > 0:
            self.fail_post_count -= 1
            return FakeHttpResponse(500, {"error": "Internal Ollama Error"})

        if self.post_response is not None:
            return self.post_response
        return FakeHttpResponse(500, {"error": "No response configured"})

    async def aclose(self) -> None:
        pass


class TestOllamaLLMClient(unittest.IsolatedAsyncioTestCase):
    """Asserts Ollama provider requests, retries, and fallbacks."""

    async def test_health_check_success(self) -> None:
        fake_http = FakeAsyncHttpClient()
        client = OllamaLLMClient(base_url="http://localhost:11434", http_client=fake_http)

        healthy = await client.check_health()
        self.assertTrue(healthy)
        self.assertEqual(len(fake_http.calls), 1)
        self.assertIn("/api/version", fake_http.calls[0]["url"])

    async def test_health_check_failure(self) -> None:
        fake_http = FakeAsyncHttpClient()
        fake_http.get_responses["/api/version"] = FakeHttpResponse(503, {"error": "service unavailable"})
        client = OllamaLLMClient(base_url="http://localhost:11434", http_client=fake_http)

        healthy = await client.check_health()
        self.assertFalse(healthy)

    async def test_list_models_and_availability(self) -> None:
        fake_http = FakeAsyncHttpClient()
        client = OllamaLLMClient(base_url="http://localhost:11434", model="holo3.1:9b", http_client=fake_http)

        models = await client.list_models()
        self.assertEqual(models, ["holo3.1:9b", "llama3:8b"])

        self.assertTrue(await client.is_model_available("holo3.1:9b"))
        self.assertTrue(await client.is_model_available("llama3:8b"))
        self.assertFalse(await client.is_model_available("gpt-4"))

    async def test_successful_generate_response_json(self) -> None:
        fake_http = FakeAsyncHttpClient()
        client = OllamaLLMClient(base_url="http://localhost:11434", model="holo3.1:9b", http_client=fake_http)

        response_text = await client.generate_response(
            system_prompt="You are a GUI agent.",
            user_prompt="Click the Submit button",
        )
        self.assertIn("target_label", response_text)
        self.assertIn("Submit", response_text)

        # Assert payload
        post_calls = [c for c in fake_http.calls if c["method"] == "POST"]
        self.assertEqual(len(post_calls), 1)
        payload = post_calls[0]["json"]
        self.assertEqual(payload["model"], "holo3.1:9b")
        self.assertEqual(payload["system"], "You are a GUI agent.")
        self.assertEqual(payload["prompt"], "Click the Submit button")
        self.assertEqual(payload["format"], "json")
        self.assertFalse(payload["stream"])

    async def test_seed_plumbed_to_options_when_set(self) -> None:
        fake_http = FakeAsyncHttpClient()
        client = OllamaLLMClient(
            base_url="http://localhost:11434",
            temperature=0,
            seed=1234,
            http_client=fake_http,
        )

        await client.generate_response(system_prompt="s", user_prompt="u")
        post_calls = [c for c in fake_http.calls if c["method"] == "POST"]
        self.assertEqual(len(post_calls), 1)
        options = post_calls[0]["json"]["options"]
        self.assertEqual(options["temperature"], 0)
        self.assertEqual(options["seed"], 1234)

    async def test_seed_absent_from_options_when_unset(self) -> None:
        fake_http = FakeAsyncHttpClient()
        client = OllamaLLMClient(base_url="http://localhost:11434", http_client=fake_http)

        await client.generate_response(system_prompt="s", user_prompt="u")
        post_calls = [c for c in fake_http.calls if c["method"] == "POST"]
        self.assertEqual(len(post_calls), 1)
        options = post_calls[0]["json"]["options"]
        self.assertEqual(options, {"temperature": 0.1})
        self.assertIsNone(client.seed)

    async def test_holo_provider_seed_passthrough(self) -> None:
        fake_http = FakeAsyncHttpClient()
        provider = HoloOllamaProvider(temperature=0, seed=99, http_client=fake_http)
        self.assertEqual(provider.seed, 99)

        await provider.generate_response(system_prompt="s", user_prompt="u")
        post_calls = [c for c in fake_http.calls if c["method"] == "POST"]
        self.assertEqual(post_calls[0]["json"]["options"]["seed"], 99)

    async def test_retry_on_transient_failure_then_success(self) -> None:
        fake_http = FakeAsyncHttpClient()
        fake_http.fail_post_count = 1  # 1 failure, then success
        client = OllamaLLMClient(
            base_url="http://localhost:11434",
            max_retries=2,
            http_client=fake_http,
        )

        response_text = await client.generate_response(
            system_prompt="system",
            user_prompt="prompt",
        )
        self.assertIn("target_label", response_text)
        post_calls = [c for c in fake_http.calls if c["method"] == "POST"]
        self.assertEqual(len(post_calls), 2)

    async def test_fallback_when_ollama_unavailable(self) -> None:
        fake_http = FakeAsyncHttpClient()
        fake_http.fail_post_count = 10  # Always fails
        fallback_mock = MockLLMClient(default_response='{"thought": "fallback plan", "action_type": "wait"}')

        client = OllamaLLMClient(
            base_url="http://localhost:11434",
            max_retries=1,
            fallback_client=fallback_mock,
            http_client=fake_http,
        )

        response_text = await client.generate_response(
            system_prompt="system",
            user_prompt="prompt",
        )
        self.assertEqual(response_text, '{"thought": "fallback plan", "action_type": "wait"}')
        self.assertEqual(len(fallback_mock.call_history), 1)

    async def test_raise_connection_error_when_no_fallback(self) -> None:
        fake_http = FakeAsyncHttpClient()
        fake_http.fail_post_count = 5
        client = OllamaLLMClient(
            base_url="http://localhost:11434",
            max_retries=1,
            fallback_client=None,
            http_client=fake_http,
        )

        with self.assertRaises(ConnectionError):
            await client.generate_response("system", "prompt")


class TestHoloOllamaProvider(unittest.IsolatedAsyncioTestCase):
    """Asserts HoloOllamaProvider pre-configuration defaults."""

    async def test_defaults(self) -> None:
        provider = HoloOllamaProvider()
        self.assertEqual(provider.model, "holo3.1:9b")
        self.assertEqual(provider.temperature, 0.1)
        self.assertEqual(provider.format, "json")
        self.assertEqual(provider.timeout_sec, 60.0)
        self.assertEqual(provider.max_retries, 2)

    async def test_holo_generation_with_mock_http(self) -> None:
        fake_http = FakeAsyncHttpClient()
        provider = HoloOllamaProvider(http_client=fake_http)

        res = await provider.generate_response(
            system_prompt="System prompt for Holo",
            user_prompt="User prompt for Holo",
        )
        self.assertIn("test plan", res)


if __name__ == "__main__":
    unittest.main()
