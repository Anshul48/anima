"""Unit tests for Entorhinal AI & LLM integration tier."""

import os
from pathlib import Path
import pytest

from entorhinal.ai.config import AIConfig, EntorhinalConfig, PolicyConfig
from entorhinal.ai.client import CloudEgressProhibitedError, LiteLLMClient
from entorhinal.ai.ollama import OllamaDetector, OllamaModelInfo
from entorhinal.policy.engine import PolicyEngine
from entorhinal.schemas.models import ClassificationLevel, EvidenceRecord, SourceType, generate_uuidv7


def test_ai_config_yaml_serialization(tmp_path: Path):
    """Test AIConfig and EntorhinalConfig YAML dump and load cycle."""
    config = EntorhinalConfig(
        version="1.0",
        storage_dir=str(tmp_path),
        ai=AIConfig(
            enabled=True,
            mode="hybrid",
            allow_cloud=True,
            primary_model="ollama/qwen3.8:27b",
            fallback_model="gemini/gemini-2.5-flash",
            fallback_api_key_env="GEMINI_API_KEY",
            temperature=0.15,
        ),
    )

    saved_path = config.save_to_dir(tmp_path)
    assert saved_path.exists()

    loaded = EntorhinalConfig.load_from_dir(tmp_path)
    assert loaded.version == "1.0"
    assert loaded.ai.mode == "hybrid"
    assert loaded.ai.primary_model == "ollama/qwen3.8:27b"
    assert loaded.ai.fallback_model == "gemini/gemini-2.5-flash"
    assert loaded.ai.temperature == 0.15


def test_ollama_detector_parse_models():
    """Test parsing of Ollama /api/tags JSON output into OllamaModelInfo."""
    detector = OllamaDetector()
    mock_data = {
        "models": [
            {
                "name": "qwen3.8:27b",
                "size": 17741872154,
                "details": {
                    "parameter_size": "27.3B",
                    "quantization_level": "Q4_K_M",
                    "family": "qwen35",
                    "context_length": 262144,
                },
                "capabilities": ["completion", "tools", "thinking", "vision"],
            },
            {
                "name": "holo-9b-64k:latest",
                "size": 5629110465,
                "details": {
                    "parameter_size": "9.0B",
                    "quantization_level": "Q4_K_M",
                    "family": "qwen35",
                    "context_length": 65536,
                },
                "capabilities": ["completion"],
            },
        ]
    }

    parsed = detector._parse_models_json(mock_data)
    assert len(parsed) == 2
    
    m1 = parsed[0]
    assert m1.name == "qwen3.8:27b"
    assert m1.model_id == "ollama/qwen3.8:27b"
    assert m1.param_size == "27.3B"
    assert m1.quant == "Q4_K_M"
    assert "tools" in m1.capabilities
    assert "qwen3.8:27b" in m1.display_label
    assert "27.3B" in m1.display_label

    m2 = parsed[1]
    assert m2.name == "holo-9b-64k:latest"
    assert m2.param_size == "9.0B"


def test_litellm_client_local_model_detection():
    """Test LiteLLMClient correctly recognizes local vs cloud model IDs."""
    client = LiteLLMClient()
    assert client.is_local_model("ollama/qwen3.8:27b") is True
    assert client.is_local_model("ollama/llama3.2") is True
    assert client.is_local_model("vllm/custom-model") is True
    assert client.is_local_model("gemini/gemini-2.5-flash") is False
    assert client.is_local_model("anthropic/claude-3-5-sonnet") is False
    assert client.is_local_model("openai/gpt-4o") is False


def test_litellm_client_airgap_enforcement():
    """Test that allow_cloud=False strictly blocks cloud model requests."""
    ai_cfg = AIConfig(
        enabled=True,
        mode="local",
        allow_cloud=False,
        primary_model="ollama/qwen2.5",
        fallback_model=None,
    )
    client = LiteLLMClient(config=ai_cfg)

    import asyncio
    with pytest.raises(CloudEgressProhibitedError):
        asyncio.run(
            client._dispatch_completion(
                model="gemini/gemini-2.5-flash",
                messages=[{"role": "user", "content": "Hello"}],
            )
        )


def test_litellm_client_pre_egress_sanitization():
    """Test that credentials in prompt text are redacted prior to cloud dispatch."""
    policy = PolicyEngine()
    client = LiteLLMClient(policy_engine=policy)

    messages = [
        {
            "role": "user",
            "content": "Here is secret: ghp_112233445566778899aabbccddeeffgghhii and AWS AKIAIOSFODNN7EXAMPLE",
        }
    ]

    sanitized = client._sanitize_messages(messages, is_cloud=True)
    content = sanitized[0]["content"]
    assert "ghp_" not in content
    assert "AKIAIOSFODNN7EXAMPLE" not in content
    assert "<REDACTED:" in content


def test_infer_task_intent_epistemic_invariants():
    """Test that infer_task_intent creates a valid bounded Hypothesis record."""
    from unittest.mock import AsyncMock

    client = LiteLLMClient()
    client.acompletion = AsyncMock(
        return_value={
            "content": '{"task_intent": "Running Test Suite", "confidence": 0.88, "reasoning_summary": "Executed pytest command"}'
        }
    )

    record = EvidenceRecord.create(
        source_type=SourceType.TERMINAL_PTY,
        app_identifier="pwsh.exe",
        window_title="Windows Terminal - pytest",
        sanitized_payload={"command": "uv run pytest tests/"},
        previous_record_hash="0" * 64,
        classification=ClassificationLevel.INTERNAL,
    )

    import asyncio
    hyp = asyncio.run(client.infer_task_intent([record]))
    assert hyp.is_hypothesis is True
    assert hyp.proposed_intent == "Running Test Suite"
    assert 0.05 <= hyp.confidence_score <= 0.95
    assert len(hyp.candidate_evidence_ids) == 1
